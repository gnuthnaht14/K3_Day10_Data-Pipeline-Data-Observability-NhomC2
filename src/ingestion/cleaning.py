from __future__ import annotations

from datetime import datetime
from typing import Iterable

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord


CLEAN_COLUMNS = [
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


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return normalize_whitespace(str(value))


def _clean_list(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _clean_text(value)
        key = item.casefold()
        if item and key not in seen:
            cleaned.append(item)
            seen.add(key)
    return cleaned


def _parse_date(value: object) -> pd.Timestamp | None:
    if value is None or not _clean_text(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed


def _run_date(run_date: datetime) -> pd.Timestamp:
    parsed = pd.to_datetime(run_date, errors="raise", utc=True)
    return parsed.normalize()


def _build_embedding_text(
    title: str,
    summary: str,
    published: str,
    authors_joined: str,
    categories_joined: str,
) -> str:
    parts = [title]
    if summary:
        parts.append(summary)
    if authors_joined:
        parts.append(f"Authors: {authors_joined}")
    if categories_joined:
        parts.append(f"Categories: {categories_joined}")
    if published:
        parts.append(f"Published: {published}")
    return normalize_whitespace(" ".join(parts))


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Build the deterministic Clean Schema consumed by retrieval and evaluation."""
    if records is None:
        records = []
    reference_date = _run_date(run_date)
    rows: list[dict[str, object]] = []

    for record in records:
        paper_id = _clean_text(getattr(record, "paper_id", "")).lower()
        title = _clean_text(getattr(record, "title", ""))
        if not paper_id or not title:
            continue

        published_date = _parse_date(getattr(record, "published", ""))
        # age_days is part of the clean contract, so records without a valid
        # publication date cannot be represented reliably and are filtered.
        if published_date is None:
            continue

        published = published_date.date().isoformat()
        age_days = max(0, int((reference_date - published_date.normalize()).days))
        authors_joined = compact_join(_clean_list(getattr(record, "authors", [])))
        categories_joined = compact_join(_clean_list(getattr(record, "categories", [])))
        summary = _clean_text(getattr(record, "summary", ""))
        text_for_embedding = _build_embedding_text(
            title=title,
            summary=summary,
            published=published,
            authors_joined=authors_joined,
            categories_joined=categories_joined,
        )
        if not text_for_embedding:
            continue

        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "published": published,
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "age_days": age_days,
                "text_for_embedding": text_for_embedding,
                "abs_url": _clean_text(getattr(record, "abs_url", "")),
                "pdf_url": _clean_text(getattr(record, "pdf_url", "")),
            }
        )

    dataframe = pd.DataFrame(rows, columns=CLEAN_COLUMNS)
    if dataframe.empty:
        dataframe = pd.DataFrame({column: pd.Series(dtype="object") for column in CLEAN_COLUMNS})
        dataframe["age_days"] = pd.Series(dtype="int64")
        return dataframe

    dataframe = (
        dataframe.drop_duplicates(subset=["paper_id"], keep="first")
        .sort_values(["paper_id", "title"], kind="mergesort")
        .reset_index(drop=True)
    )
    dataframe["age_days"] = dataframe["age_days"].astype("int64")
    return dataframe[CLEAN_COLUMNS]
