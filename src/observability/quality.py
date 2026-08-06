from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import safe_slug, write_json


_SUMMARY_MIN_CHARS = 80


def _json_value(value: Any) -> Any:
    """Convert pandas/numpy values to values accepted by ``json.dumps``."""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _examples(df: pd.DataFrame, mask: pd.Series, columns: list[str]) -> list[dict[str, Any]]:
    """Return a small, serialisable sample of records that failed a check."""
    available_columns = [column for column in columns if column in df.columns]
    if not available_columns:
        return []
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in df.loc[mask, available_columns].head(5).to_dict(orient="records")
    ]


def _check(
    name: str,
    description: str,
    failure_mask: pd.Series,
    expected: str,
    df: pd.DataFrame,
    example_columns: list[str],
) -> dict[str, Any]:
    """Build one consistently shaped check result from its failing-row mask."""
    failed_rows = int(failure_mask.fillna(True).sum())
    return {
        "name": name,
        "description": description,
        "status": "passed" if failed_rows == 0 else "failed",
        "expected": expected,
        "failed_rows": failed_rows,
        "failed_examples": _examples(df, failure_mask.fillna(True), example_columns),
    }


def _published_timestamps(df: pd.DataFrame) -> pd.Series:
    if "published" not in df.columns:
        return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    return pd.to_datetime(df["published"], errors="coerce", utc=True)


def _age_days(df: pd.DataFrame, published: pd.Series) -> pd.Series:
    """Use the saved age field when possible; otherwise derive it from publication date."""
    if "age_days" in df.columns:
        ages = pd.to_numeric(df["age_days"], errors="coerce")
        if ages.notna().any():
            return ages
    today = pd.Timestamp(datetime.now(UTC).date(), tz="UTC")
    return (today - published).dt.days.astype("float64")


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """TODO(student): tao bo data quality checks.

    Pseudo-code:
    1. Check row count.
    2. Check `paper_id` not null va unique.
    3. Check `title` not null.
    4. Check do dai `summary`.
    5. Check freshness bang `age_days`.
    6. Ghi ket qua vao `data/quality/`.
    """
    # Keep each check independent so one missing column is reported as a data
    # quality failure instead of making the observability stage crash.
    required_columns = {"paper_id", "title", "summary", "published", "age_days"}
    missing_columns = sorted(required_columns - set(df.columns))
    checks: list[dict[str, Any]] = [
        {
            "name": "required_columns_present",
            "description": "The cleaned dataset exposes fields required by indexing and monitoring.",
            "status": "passed" if not missing_columns else "failed",
            "expected": ", ".join(sorted(required_columns)),
            "missing_columns": missing_columns,
            "failed_rows": 0 if not missing_columns else int(len(df)),
            "failed_examples": [],
        },
        {
            "name": "row_count",
            "description": "The cleaned dataset contains at least one record.",
            "status": "passed" if len(df) > 0 else "failed",
            "expected": "> 0 rows",
            "observed_value": int(len(df)),
            "failed_rows": 0 if len(df) > 0 else 1,
            "failed_examples": [],
        },
    ]

    paper_ids = df.get("paper_id", pd.Series(pd.NA, index=df.index, dtype="object"))
    paper_id_missing = paper_ids.isna() | paper_ids.astype("string").str.strip().eq("")
    checks.append(
        _check(
            "paper_id_not_null",
            "Every paper must have a non-empty stable identifier.",
            paper_id_missing,
            "0 missing paper_id values",
            df,
            ["paper_id", "title"],
        )
    )
    duplicate_ids = paper_ids.astype("string").str.strip().duplicated(keep=False) & ~paper_id_missing
    checks.append(
        _check(
            "paper_id_unique",
            "Paper identifiers must be unique after cleaning.",
            duplicate_ids,
            "0 duplicate non-empty paper_id values",
            df,
            ["paper_id", "title"],
        )
    )

    titles = df.get("title", pd.Series(pd.NA, index=df.index, dtype="object"))
    title_missing = titles.isna() | titles.astype("string").str.strip().eq("")
    checks.append(
        _check(
            "title_not_null",
            "Every paper must have a non-empty title.",
            title_missing,
            "0 missing title values",
            df,
            ["paper_id", "title"],
        )
    )

    summaries = df.get("summary", pd.Series(pd.NA, index=df.index, dtype="object"))
    summary_lengths = summaries.astype("string").str.strip().str.len()
    short_summary = summaries.isna() | summary_lengths.lt(_SUMMARY_MIN_CHARS)
    summary_check = _check(
        "summary_min_length",
        "Summaries retain enough content to produce meaningful embedding context.",
        short_summary,
        f"summary length >= {_SUMMARY_MIN_CHARS} characters",
        df,
        ["paper_id", "title", "summary"],
    )
    summary_check["min_characters"] = _SUMMARY_MIN_CHARS
    summary_check["observed_min_characters"] = (
        None if summary_lengths.dropna().empty else int(summary_lengths.dropna().min())
    )
    checks.append(summary_check)

    published = _published_timestamps(df)
    ages = _age_days(df, published)
    invalid_age = ages.isna() | ages.lt(0)
    checks.append(
        _check(
            "age_days_valid",
            "Freshness ages are present numeric values and not in the future.",
            invalid_age,
            "age_days is a non-negative number",
            df,
            ["paper_id", "published", "age_days"],
        )
    )
    stale_rows = ages.gt(settings.freshness_threshold_days)
    freshness_check = _check(
        "freshness_threshold",
        "No record is older than the configured freshness threshold.",
        stale_rows,
        f"age_days <= {settings.freshness_threshold_days}",
        df,
        ["paper_id", "title", "published", "age_days"],
    )
    freshness_check["threshold_days"] = settings.freshness_threshold_days
    checks.append(freshness_check)

    failed_checks = [check["name"] for check in checks if check["status"] == "failed"]
    report = {
        "report_name": report_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_rows": int(len(df)),
        "status": "passed" if not failed_checks else "failed",
        "passed_checks": len(checks) - len(failed_checks),
        "failed_checks": failed_checks,
        "checks": checks,
    }
    report_path = settings.paths.quality_dir / f"{safe_slug(report_name)}_quality.json"
    write_json(report_path, report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """TODO(student): tong hop freshness report.

    Pseudo-code:
    1. Tim latest va oldest published date.
    2. Dem so dong stale.
    3. Tao payload:
       - latest_published
       - oldest_published
       - stale_rows
       - total_rows
       - is_fresh
    4. Ghi JSON report.
    """
    published = _published_timestamps(df)
    ages = _age_days(df, published)
    invalid_dates = published.isna()
    stale = ages.gt(settings.freshness_threshold_days)
    valid_dates = published.dropna()

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "threshold_days": settings.freshness_threshold_days,
        "latest_published": None if valid_dates.empty else valid_dates.max().date().isoformat(),
        "oldest_published": None if valid_dates.empty else valid_dates.min().date().isoformat(),
        "stale_rows": int(stale.sum()),
        "invalid_published_rows": int(invalid_dates.sum()),
        "total_rows": int(len(df)),
        "is_fresh": bool(len(df) > 0 and not stale.any() and not invalid_dates.any()),
        "status": "passed" if len(df) > 0 and not stale.any() and not invalid_dates.any() else "failed",
        "stale_examples": _examples(
            df,
            stale,
            ["paper_id", "title", "published", "age_days"],
        ),
    }
    write_json(Path(report_path), report)
    return report
