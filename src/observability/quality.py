from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


REQUIRED_CLEAN_COLUMNS = (
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
)
MIN_SUMMARY_CHARS = 20


def _check(
    name: str,
    value: Any,
    threshold: Any,
    passed: bool,
    details: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "value": value,
        "threshold": threshold,
        "passed": bool(passed),
    }
    if details:
        result["details"] = details
    return result


def _quality_path(settings: Settings, report_name: str) -> Path:
    name = Path(str(report_name)).name
    if not name or name in {".", ".."}:
        raise ValueError("report_name must be a non-empty file name.")
    if Path(name).suffix.lower() != ".json":
        name = f"{name}.json"
    return Path(settings.paths.quality_dir) / name


def _age_series(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if "age_days" not in df.columns:
        empty = pd.Series(index=df.index, dtype="float64")
        return empty, pd.Series(True, index=df.index)
    numeric = pd.to_numeric(df["age_days"], errors="coerce")
    invalid = numeric.isna() | numeric.lt(0) | numeric.mod(1).ne(0)
    return numeric, invalid


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run non-mutating quality checks and persist a JSON quality artifact."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")

    missing_columns = [column for column in REQUIRED_CLEAN_COLUMNS if column not in df.columns]
    checks: list[dict[str, Any]] = []
    row_count = int(len(df))
    checks.append(_check("row_count", row_count, {"min": 1}, row_count >= 1))
    checks.append(
        _check(
            "required_schema",
            missing_columns,
            {"required_columns": list(REQUIRED_CLEAN_COLUMNS)},
            not missing_columns,
        )
    )

    if "paper_id" in df.columns:
        paper_ids = df["paper_id"]
        null_or_empty = int(
            (paper_ids.isna() | paper_ids.fillna("").astype(str).str.strip().eq("")).sum()
        )
        duplicate_rows = int(paper_ids.duplicated(keep=False).sum())
    else:
        null_or_empty = row_count
        duplicate_rows = 0
    checks.append(_check("paper_id_not_null", null_or_empty, 0, null_or_empty == 0))
    checks.append(_check("paper_id_unique", duplicate_rows, 0, duplicate_rows == 0))
    checks.append(_check("duplicate_rows", duplicate_rows, 0, duplicate_rows == 0))

    if "title" in df.columns:
        empty_titles = int(df["title"].fillna("").astype(str).str.strip().eq("").sum())
    else:
        empty_titles = row_count
    checks.append(_check("title_not_empty", empty_titles, 0, empty_titles == 0))

    if "summary" in df.columns:
        summary_lengths = df["summary"].fillna("").astype(str).str.strip().str.len()
        short_summaries = int(summary_lengths.lt(MIN_SUMMARY_CHARS).sum())
    else:
        short_summaries = row_count
    checks.append(
        _check(
            "summary_min_length",
            short_summaries,
            {"min_chars": MIN_SUMMARY_CHARS, "max_rows_below_threshold": 0},
            short_summaries == 0,
        )
    )

    if "text_for_embedding" in df.columns:
        empty_embedding_text = int(df["text_for_embedding"].fillna("").astype(str).str.strip().eq("").sum())
    else:
        empty_embedding_text = row_count
    checks.append(_check("text_for_embedding_not_empty", empty_embedding_text, 0, empty_embedding_text == 0))

    ages, invalid_age = _age_series(df)
    invalid_age_count = int(invalid_age.sum())
    checks.append(_check("age_days_valid", invalid_age_count, 0, invalid_age_count == 0))
    stale_rows = int((~invalid_age & ages.gt(int(settings.freshness_threshold_days))).sum())
    checks.append(
        _check(
            "stale_rows",
            stale_rows,
            {"max_age_days": int(settings.freshness_threshold_days), "max_rows": 0},
            stale_rows == 0,
        )
    )

    passed_checks = sum(1 for check in checks if check["passed"])
    failed_checks = [check["name"] for check in checks if not check["passed"]]
    report: dict[str, Any] = {
        "report_name": str(report_name),
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "pass" if not failed_checks else "fail",
        "passed": not failed_checks,
        "total_rows": row_count,
        "checks": checks,
        "summary": {
            "total_checks": len(checks),
            "passed_checks": passed_checks,
            "failed_checks": len(failed_checks),
            "failed_check_names": failed_checks,
        },
    }
    write_json(_quality_path(settings, report_name), report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Build a freshness artifact without changing the input dataframe."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")

    total_rows = int(len(df))
    if "published" not in df.columns:
        published = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    else:
        published = pd.to_datetime(df["published"], errors="coerce", utc=True)

    valid_dates = published.notna()
    invalid_published_rows = int((~valid_dates).sum())
    today = pd.Timestamp.now(tz="UTC").normalize()
    age_days = (today - published.dt.normalize()).dt.days
    stale_mask = valid_dates & age_days.gt(int(settings.freshness_threshold_days))
    stale_rows = int(stale_mask.sum())

    valid_values = published[valid_dates]
    latest_published = valid_values.max().date().isoformat() if not valid_values.empty else None
    oldest_published = valid_values.min().date().isoformat() if not valid_values.empty else None

    if total_rows == 0:
        status = "empty"
    elif invalid_published_rows:
        status = "invalid"
    elif stale_rows:
        status = "stale"
    else:
        status = "fresh"

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "latest_published": latest_published,
        "oldest_published": oldest_published,
        "stale_rows": stale_rows,
        "invalid_published_rows": invalid_published_rows,
        "total_rows": total_rows,
        "threshold_days": int(settings.freshness_threshold_days),
        "is_fresh": status == "fresh",
        "status": status,
    }
    write_json(Path(report_path), report)
    return report
