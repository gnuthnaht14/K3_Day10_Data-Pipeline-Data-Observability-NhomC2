from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import html
import os
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json


CROSSREF_API_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _text(value: Any) -> str:
    """Convert Crossref text (including simple JATS/HTML) to plain text."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    cleaned = html.unescape(str(value))
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return normalize_whitespace(cleaned)


def _first_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        for item in value:
            result = _text(item)
            if result:
                return result
        return ""
    return _text(value)


def _date_from_item(item: dict[str, Any] | None) -> str:
    """Format Crossref date-parts as an ISO date with safe defaults."""
    if not isinstance(item, dict):
        return ""
    parts = item.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list) or not parts[0]:
        return ""
    try:
        values = [int(value) for value in parts[0][:3]]
        year = values[0]
        month = values[1] if len(values) >= 2 else 1
        day = values[2] if len(values) >= 3 else 1
        return date(year, month, day).isoformat()
    except (TypeError, ValueError, OverflowError):
        return ""


def _published_date(item: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "published", "issued"):
        value = _date_from_item(item.get(key))
        if value:
            return value
    return ""


def _authors(item: dict[str, Any]) -> list[str]:
    authors = item.get("author", [])
    if not isinstance(authors, list):
        return []

    result: list[str] = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = _text(author.get("name"))
        if not name:
            given = _text(author.get("given"))
            family = _text(author.get("family"))
            name = normalize_whitespace(f"{given} {family}")
        if name:
            result.append(name)
    return result


def _pdf_url(item: dict[str, Any]) -> str:
    links = item.get("link", [])
    if isinstance(links, list):
        for link in links:
            if not isinstance(link, dict):
                continue
            content_type = _text(link.get("content-type")).lower()
            url = _text(link.get("URL") or link.get("url"))
            if url and (content_type == "application/pdf" or url.lower().split("?", 1)[0].endswith(".pdf")):
                return url
    return ""


def _record_from_item(item: dict[str, Any]) -> PaperRecord | None:
    paper_id = _text(item.get("DOI") or item.get("doi")).lower()
    title = _first_text(item.get("title"))
    if not paper_id or not title:
        return None

    categories = item.get("subject", [])
    if not isinstance(categories, list):
        categories = []
    categories = [_text(category) for category in categories]
    categories = [category for category in categories if category]

    return PaperRecord(
        paper_id=paper_id,
        title=title,
        summary=_text(item.get("abstract")),
        authors=_authors(item),
        categories=categories,
        primary_category=categories[0] if categories else "",
        published=_published_date(item),
        updated=_date_from_item(item.get("updated")),
        abs_url=_text(item.get("URL") or item.get("url")),
        pdf_url=_pdf_url(item),
        comment=_text(item.get("comment")),
    )


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse a Crossref response into deduplicated :class:`PaperRecord` values."""
    if not isinstance(payload, dict):
        return []
    message = payload.get("message")
    if not isinstance(message, dict):
        return []
    items = message.get("items", [])
    if not isinstance(items, list):
        return []

    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        record = _record_from_item(item)
        if record is None or record.paper_id in seen_ids:
            continue
        seen_ids.add(record.paper_id)
        records.append(record)
    return records


def _endpoint(settings: Settings) -> str:
    configured = str(getattr(settings, "source_api", "") or "").strip()
    return configured if configured.startswith(("http://", "https://")) else CROSSREF_API_URL


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After") if response is not None else None
    try:
        if retry_after is not None:
            return max(0.0, min(float(retry_after), 30.0))
    except (TypeError, ValueError):
        pass
    configured = os.getenv("CROSSREF_BACKOFF_SECONDS", "1")
    try:
        base = max(0.0, float(configured))
    except ValueError:
        base = 1.0
    return base * (2**attempt)


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch Crossref data, persist the raw payload and parsed record snapshot."""
    params = {
        "query.bibliographic": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }
    headers = {
        "Accept": "application/json",
        "User-Agent": "day10-data-observability-lab/1.0 (Crossref client)",
    }

    response: requests.Response | None = None
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(
                _endpoint(settings),
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= MAX_RETRIES:
                raise RuntimeError("Crossref request failed after retries.") from exc
            time.sleep(_retry_delay(response, attempt))
            continue

        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
            time.sleep(_retry_delay(response, attempt))
            continue
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Crossref request failed with HTTP {response.status_code}.") from exc
        break
    else:  # pragma: no cover - loop always either breaks or raises
        raise RuntimeError("Crossref request failed.") from last_error

    if response is None:  # pragma: no cover - defensive guard
        raise RuntimeError("Crossref returned no response.")
    try:
        payload = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError) as exc:
        raise ValueError("Crossref response is not valid JSON.") from exc

    write_json(Path(settings.paths.raw_api_response), payload)
    records = parse_crossref_payload(payload)
    write_json(Path(settings.paths.raw_records_json), [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load and validate a JSON raw-record snapshot."""
    payload = read_json(Path(path))
    if not isinstance(payload, list):
        raise ValueError(f"Raw records must be a JSON array: {path}")

    field_names = set(PaperRecord.__dataclass_fields__)
    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Raw record at index {index} must be an object.")
        missing = field_names.difference(item)
        if missing:
            missing_fields = ", ".join(sorted(missing))
            raise ValueError(f"Raw record at index {index} is missing: {missing_fields}")
        if any(item[field] is None for field in field_names):
            raise ValueError(f"Raw record at index {index} contains null fields.")
        if not isinstance(item["authors"], list) or not isinstance(item["categories"], list):
            raise ValueError(f"Raw record at index {index} has invalid list fields.")
        if not all(isinstance(value, str) for value in item["authors"] + item["categories"]):
            raise ValueError(f"Raw record at index {index} has non-string list values.")
        record = PaperRecord(
            paper_id=_text(item["paper_id"]).lower(),
            title=_text(item["title"]),
            summary=_text(item["summary"]),
            authors=list(item["authors"]),
            categories=list(item["categories"]),
            primary_category=_text(item["primary_category"]),
            published=_text(item["published"]),
            updated=_text(item["updated"]),
            abs_url=_text(item["abs_url"]),
            pdf_url=_text(item["pdf_url"]),
            comment=_text(item["comment"]),
        )
        if not record.paper_id or not record.title:
            raise ValueError(f"Raw record at index {index} has empty paper_id/title.")
        if record.paper_id in seen_ids:
            raise ValueError(f"Duplicate paper_id in raw records: {record.paper_id}")
        seen_ids.add(record.paper_id)
        records.append(record)
    return records
