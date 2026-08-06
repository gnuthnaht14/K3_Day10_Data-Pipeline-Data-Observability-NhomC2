from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import random
from typing import Iterable

import pandas as pd

from core.utils import normalize_whitespace, write_json
from ingestion.cleaning import CLEAN_COLUMNS


CORRUPTION_SEED = 42
CORRUPTION_MARKER = "[CORRUPTION_NOISE_SEED_42]"
CORRUPTION_NOISE_TEXT = (
    f"{CORRUPTION_MARKER} Unrelated weather sports cooking finance content "
    "that does not describe this scholarly paper."
)
DEFAULT_SCENARIOS = (
    "drop_eval_record",
    "blank_summary",
    "inject_embedding_noise",
    "make_published_date_stale",
    "add_duplicate_rows",
)


def _validate_input(df: pd.DataFrame) -> None:
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")
    missing = [column for column in CLEAN_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Clean dataframe is missing required columns: {', '.join(missing)}")
    if df.empty:
        raise ValueError("Cannot create corruption from an empty clean dataframe.")


def _rebuild_text(row: pd.Series) -> str:
    parts = [str(row.get("title", "") or "").strip()]
    summary = str(row.get("summary", "") or "").strip()
    authors = str(row.get("authors_joined", "") or "").strip()
    categories = str(row.get("categories_joined", "") or "").strip()
    published = str(row.get("published", "") or "").strip()
    if summary:
        parts.append(summary)
    if authors:
        parts.append(f"Authors: {authors}")
    if categories:
        parts.append(f"Categories: {categories}")
    if published:
        parts.append(f"Published: {published}")
    return normalize_whitespace(" ".join(part for part in parts if part))


def _recompute_derived_columns(df: pd.DataFrame) -> None:
    published = pd.to_datetime(df["published"], errors="coerce", utc=True)
    today = pd.Timestamp.now(tz="UTC").normalize()
    age_days = (today - published.dt.normalize()).dt.days
    df["age_days"] = age_days.fillna(0).clip(lower=0).astype("int64")
    df["text_for_embedding"] = df.apply(_rebuild_text, axis=1)


def _normalized_eval_ids(eval_doc_ids: Iterable[str] | None) -> list[str]:
    return sorted({str(value).strip() for value in (eval_doc_ids or []) if str(value).strip()})


def _target_index(
    df: pd.DataFrame,
    eval_doc_ids: Iterable[str] | None,
    offset: int,
    seed: int,
) -> int:
    eval_ids = _normalized_eval_ids(eval_doc_ids)
    paper_ids = df["paper_id"].astype(str)
    matching = [int(index) for index in df.index if paper_ids.loc[index] in eval_ids]
    if matching:
        return matching[offset % len(matching)]
    candidates = [int(index) for index in df.index]
    return random.Random(seed + offset).choice(candidates)


def _operation(scenario: str, record_ids: list[str], eval_doc_ids: Iterable[str] | None, **parameters) -> dict:
    eval_ids = set(_normalized_eval_ids(eval_doc_ids))
    affected_eval_ids = sorted(set(record_ids).intersection(eval_ids))
    return {
        "type": scenario,
        "record_ids": record_ids,
        "affected_count": len(record_ids),
        "affected_eval_doc_ids": affected_eval_ids,
        "overlap_with_eval": bool(affected_eval_ids),
        "parameters": parameters,
    }


def apply_corruption_scenario(
    df: pd.DataFrame,
    scenario: str,
    eval_doc_ids: Iterable[str] | None = None,
    seed: int = CORRUPTION_SEED,
) -> tuple[pd.DataFrame, dict]:
    """Apply one deterministic scenario and return its auditable operation record."""
    _validate_input(df)
    working = df.copy(deep=True).reset_index(drop=True)

    if scenario == "drop_eval_record":
        index = _target_index(working, eval_doc_ids, offset=2, seed=seed)
        record_id = str(working.at[index, "paper_id"])
        working = working.drop(index=index).reset_index(drop=True)
        operation = _operation(scenario, [record_id], eval_doc_ids, count=1, seed=seed)
    elif scenario == "blank_summary":
        index = _target_index(working, eval_doc_ids, offset=0, seed=seed)
        record_id = str(working.at[index, "paper_id"])
        working.at[index, "summary"] = ""
        operation = _operation(scenario, [record_id], eval_doc_ids, replacement="", seed=seed)
    elif scenario == "inject_embedding_noise":
        index = _target_index(working, eval_doc_ids, offset=1, seed=seed)
        record_id = str(working.at[index, "paper_id"])
        original = str(working.at[index, "summary"] or "").strip()
        working.at[index, "summary"] = normalize_whitespace(f"{CORRUPTION_NOISE_TEXT} {original}")
        operation = _operation(
            scenario,
            [record_id],
            eval_doc_ids,
            marker=CORRUPTION_MARKER,
            target_column="text_for_embedding",
            seed=seed,
        )
    elif scenario == "make_published_date_stale":
        index = _target_index(working, eval_doc_ids, offset=0, seed=seed)
        record_id = str(working.at[index, "paper_id"])
        working.at[index, "published"] = "2000-01-01"
        operation = _operation(
            scenario,
            [record_id],
            eval_doc_ids,
            replacement_date="2000-01-01",
            seed=seed,
        )
    elif scenario == "add_duplicate_rows":
        index = _target_index(working, eval_doc_ids, offset=1, seed=seed)
        record_id = str(working.at[index, "paper_id"])
        working = pd.concat([working, working.iloc[[index]].copy()], ignore_index=True)
        operation = _operation(scenario, [record_id], eval_doc_ids, count=1, seed=seed)
    else:
        raise ValueError(f"Unsupported corruption scenario: {scenario}")

    _recompute_derived_columns(working)
    return working[CLEAN_COLUMNS], operation


def corrupt_clean_dataframe(
    df: pd.DataFrame,
    output_log_path,
    eval_doc_ids: Iterable[str] | None = None,
    scenarios: Iterable[str] | None = None,
    test_set_sha256: str | None = None,
) -> pd.DataFrame:
    """Create deterministic corruption that explicitly overlaps the frozen eval set."""
    _validate_input(df)
    input_rows = int(len(df))
    selected_scenarios = tuple(scenarios or DEFAULT_SCENARIOS)
    if len(selected_scenarios) < 3:
        raise ValueError("At least three corruption scenarios are required.")

    working = df.copy(deep=True).reset_index(drop=True)
    operations: list[dict] = []
    for scenario in selected_scenarios:
        working, operation = apply_corruption_scenario(
            working,
            scenario,
            eval_doc_ids=eval_doc_ids,
            seed=CORRUPTION_SEED,
        )
        operations.append(operation)

    affected_eval_doc_ids = sorted(
        {
            paper_id
            for operation in operations
            for paper_id in operation["affected_eval_doc_ids"]
        }
    )
    eval_ids = _normalized_eval_ids(eval_doc_ids)
    if eval_ids and not affected_eval_doc_ids:
        raise RuntimeError("Controlled corruption did not overlap the frozen evaluation set.")
    if CORRUPTION_MARKER not in " ".join(working["text_for_embedding"].astype(str)):
        raise RuntimeError("Embedding-noise scenario did not reach text_for_embedding.")

    log = {
        "generated_at": datetime.now(UTC).isoformat(),
        "seed": CORRUPTION_SEED,
        "test_set_sha256": test_set_sha256,
        "input_rows": input_rows,
        "output_rows": int(len(working)),
        "overlap_with_eval": bool(affected_eval_doc_ids),
        "affected_eval_doc_ids": affected_eval_doc_ids,
        "operations": operations,
        "summary": {
            "operations_count": len(operations),
            "scenarios": list(selected_scenarios),
            "rows_delta": int(len(working)) - input_rows,
        },
    }
    write_json(Path(output_log_path), log)
    return working[CLEAN_COLUMNS]
