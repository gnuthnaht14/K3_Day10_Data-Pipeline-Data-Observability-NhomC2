from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime
from hashlib import sha256
from typing import Any

import pandas as pd

from ingestion.crossref import PaperRecord


OUTPUT_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "published",
    "authors_joined",
    "categories_joined",
    "age_days",
    "text_for_embedding",
    "abs_url",
    "pdf_url",
]

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MOJIBAKE_MARKERS = ("Ã", "Â", "Ð", "Ñ", "â", "ð")
_MAX_SUMMARY_CHARS = 100_000
_UNKNOWN_VALUE = "unknown"


def _repair_mojibake(value: str) -> str:
    """Repair the common UTF-8-read-as-Latin-1 artifact without touching normal text."""
    if not any(marker in value for marker in _MOJIBAKE_MARKERS):
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired if sum(value.count(marker) for marker in _MOJIBAKE_MARKERS) > sum(
        repaired.count(marker) for marker in _MOJIBAKE_MARKERS
    ) else value


def _clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = _repair_mojibake(str(value))
    text = html.unescape(text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _CONTROL_RE.sub(" ", text)
    # NFC keeps Vietnamese combining marks in a stable representation.
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_list(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, str):
        value = [value]
    return [item for item in (_clean_text(item) for item in value) if item]


def _is_missing(value: Any) -> bool:
    return value is None or _clean_text(value).casefold() in {"", "n/a", "null", "none"}


def _parse_date(value: Any) -> pd.Timestamp | None:
    if _is_missing(value):
        return None
    text = _clean_text(value)
    # Parse the ambiguous slash format explicitly to avoid locale-dependent behavior.
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", text):
        parsed = pd.to_datetime(text, format="%d/%m/%Y", errors="coerce")
    else:
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).normalize()


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Build the clean data contract consumed by indexing and evaluation.

    Required fields (paper_id, title, summary and published) are dropped when
    missing or invalid. Optional fields are represented by empty strings so
    downstream CSV/JSON consumers never receive NULL values.
    """
    run_day = pd.Timestamp(run_date).normalize()
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_content: set[str] = set()

    for record in records:
        paper_id = _clean_text(getattr(record, "paper_id", ""))
        title = _clean_text(getattr(record, "title", ""))
        summary = _clean_text(getattr(record, "summary", ""))
        published = _parse_date(getattr(record, "published", ""))

        # Mandatory completeness/validity checks and the requested 100-char rule.
        if _is_missing(paper_id) or _is_missing(title) or len(summary) < 100 or published is None:
            continue
        if len(summary) > _MAX_SUMMARY_CHARS:
            # Pathological payloads are not useful for embeddings and can exhaust
            # model input limits; discard them as embedding-quality outliers.
            continue

        normalized_id = paper_id.casefold()
        content_key = sha256(f"{title.casefold()}\n{summary.casefold()}".encode("utf-8")).hexdigest()
        if normalized_id in seen_ids or content_key in seen_content:
            continue
        seen_ids.add(normalized_id)
        seen_content.add(content_key)

        authors = ", ".join(_clean_list(getattr(record, "authors", []))) or _UNKNOWN_VALUE
        categories = ", ".join(_clean_list(getattr(record, "categories", [])))
        if not categories:
            # Crossref often omits ``subject``. Preserve the missingness
            # explicitly instead of emitting an ambiguous empty value.
            categories = _clean_text(getattr(record, "primary_category", "")) or _UNKNOWN_VALUE
        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "published": published.strftime("%Y-%m-%d"),
                "authors_joined": authors,
                "categories_joined": categories,
                "age_days": int((run_day - published).days),
                "text_for_embedding": (
                    f"Title: {title} | Authors: {authors} | Summary: {summary}"
                ),
                "abs_url": _clean_text(getattr(record, "abs_url", "")) or _UNKNOWN_VALUE,
                "pdf_url": _clean_text(getattr(record, "pdf_url", "")) or _UNKNOWN_VALUE,
            }
        )

    result = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if result.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return result.sort_values(["published", "paper_id"], kind="stable").reset_index(drop=True)


def save_clean_outputs(df: pd.DataFrame, csv_path: str | Any, json_path: str | Any) -> None:
    """Persist a clean dataframe using UTF-8 and a stable JSON record shape."""
    output = df.reindex(columns=OUTPUT_COLUMNS).copy()
    output.to_csv(csv_path, index=False, encoding="utf-8")
    output.to_json(json_path, orient="records", force_ascii=False, indent=2)
