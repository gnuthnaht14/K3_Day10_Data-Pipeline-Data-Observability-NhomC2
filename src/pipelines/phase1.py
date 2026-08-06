from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import load_settings
from core.utils import file_sha256, now_utc, read_json, write_csv, write_json
from evaluation.metrics import EvaluationBundle, evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import CLEAN_COLUMNS, build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.agent import build_agent_answerer
from retrieval.index import LocalEmbeddingIndex


def validate_clean_dataframe(df: pd.DataFrame, label: str = "clean") -> None:
    """Fail fast when a pipeline boundary does not satisfy the Clean Schema."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"{label} dataframe must be a pandas DataFrame.")
    missing = [column for column in CLEAN_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"{label} dataframe is missing columns: {', '.join(missing)}")
    if df.empty:
        raise ValueError(f"{label} dataframe is empty.")
    if df["paper_id"].isna().any() or df["paper_id"].astype(str).str.strip().eq("").any():
        raise ValueError(f"{label} dataframe contains null or empty paper_id values.")
    if not df["paper_id"].is_unique:
        raise ValueError(f"{label} dataframe contains duplicate paper_id values.")
    if df["text_for_embedding"].fillna("").astype(str).str.strip().eq("").any():
        raise ValueError(f"{label} dataframe contains empty text_for_embedding values.")


def validate_evaluation_set(path: Path, paper_ids: set[str]) -> list[dict[str, Any]]:
    """Validate a fixed evaluation set before any baseline/comparison run."""
    payload = read_json(path)
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Evaluation set must be a non-empty JSON array: {path}")
    required = {"id", "question_type", "question", "ground_truth", "ground_truth_doc_ids"}
    seen_ids: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError(f"Evaluation item {index} has an invalid schema: {path}")
        item_id = str(item["id"])
        if item_id in seen_ids:
            raise ValueError(f"Duplicate evaluation item id: {item_id}")
        seen_ids.add(item_id)
        doc_ids = item["ground_truth_doc_ids"]
        if not isinstance(doc_ids, list) or not doc_ids or not all(str(doc_id) in paper_ids for doc_id in doc_ids):
            raise ValueError(f"Evaluation item {item_id} references an unknown paper_id.")
    return payload


def save_clean_dataframe(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    validate_clean_dataframe(df)
    write_csv(df, csv_path)
    write_json(json_path, df.to_dict(orient="records"))


def load_or_build_evaluation_set(settings, clean_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Create the evaluation artifact once, then validate and reuse it unchanged."""
    eval_path = Path(settings.paths.eval_testset)
    if settings.refresh_test_set or not eval_path.exists():
        build_test_set(clean_df, eval_path)
    return validate_evaluation_set(eval_path, set(clean_df["paper_id"].astype(str)))


def _load_or_fetch_records(settings) -> tuple[list, str]:
    raw_path = Path(settings.paths.raw_records_json)
    if settings.refresh_source or not raw_path.exists():
        return fetch_source_records(settings), "fetched"
    return load_raw_records(raw_path), "loaded_snapshot"


def _source_summary(settings, source_mode: str, raw_count: int, clean_count: int) -> dict[str, Any]:
    return {
        "source_api": settings.source_api,
        "source_query": settings.source_query,
        "source_filter": settings.source_filter,
        "load_mode": source_mode,
        "raw_records": raw_count,
        "clean_records": clean_count,
        "raw_response_path": str(settings.paths.raw_api_response),
        "raw_records_path": str(settings.paths.raw_records_json),
        "clean_csv_path": str(settings.paths.clean_csv),
        "clean_json_path": str(settings.paths.clean_json),
        "test_set_path": str(settings.paths.eval_testset),
        "test_set_sha256": file_sha256(settings.paths.eval_testset),
        "answerer": "LangChain tool-calling agent with independent semantic retrieval trace",
        "generated_at": datetime.now(UTC).isoformat(),
    }

def main() -> None:
    """Run the reproducible clean-data baseline from raw source to report."""
    settings = load_settings()
    records, source_mode = _load_or_fetch_records(settings)
    clean_df = build_clean_dataframe(records, now_utc())
    validate_clean_dataframe(clean_df, "baseline clean")
    save_clean_dataframe(clean_df, settings.paths.clean_csv, settings.paths.clean_json)

    index = LocalEmbeddingIndex.build(
        clean_df,
        settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )

    eval_path = Path(settings.paths.eval_testset)
    eval_payload = load_or_build_evaluation_set(settings, clean_df)

    bundle: EvaluationBundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=eval_path,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
        answerer=build_agent_answerer(settings, index),
    )
    quality = run_data_quality_checks(clean_df, settings, "baseline")
    freshness = build_freshness_report(clean_df, settings, settings.paths.freshness_report)
    generate_phase1_report(
        report_path=settings.paths.baseline_report,
        source_summary=_source_summary(settings, source_mode, len(records), len(clean_df)),
        metrics=bundle.summary,
        quality=quality,
        freshness=freshness,
    )

    print(f"Phase 1 complete: raw={len(records)}, clean={len(clean_df)}, eval={len(eval_payload)}")
    print(f"Baseline metrics: {settings.paths.baseline_metrics}")
    print(f"Baseline report: {settings.paths.baseline_report}")
