from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.config import load_settings
from core.utils import file_sha256, now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_core_metrics, evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import DEFAULT_SCENARIOS, apply_corruption_scenario, corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.agent import build_agent_answerer
from retrieval.index import LocalEmbeddingIndex
from pipelines.phase1 import validate_clean_dataframe, validate_evaluation_set


def _require_artifact(path: Path, description: str) -> None:
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Missing {description}: {path}. Run `uv run python script/run_phase1.py` first."
        )


def _freshness_path(settings, label: str) -> Path:
    return Path(settings.paths.quality_dir) / f"freshness_{label}.json"


def _validate_pipeline_columns(df: pd.DataFrame, label: str) -> None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        raise ValueError(f"{label} dataframe must be a non-empty DataFrame.")
    required = {
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
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"{label} dataframe is missing columns: {', '.join(missing)}")


def _save_dataframe(df: pd.DataFrame, csv_path: Path, json_path: Path, label: str) -> None:
    _validate_pipeline_columns(df, label)
    write_csv(df, csv_path)
    write_json(json_path, df.to_dict(orient="records"))


def _load_corrupted_csv(path: Path) -> pd.DataFrame:
    """Consume the persisted corruption artifact without turning blanks into NaN."""
    frame = pd.read_csv(path, keep_default_na=False)
    _validate_pipeline_columns(frame, "persisted corrupted clean")
    return frame


def _evaluation_doc_ids(eval_payload: list[dict]) -> set[str]:
    return {
        str(doc_id)
        for item in eval_payload
        for doc_id in item.get("ground_truth_doc_ids", [])
    }


def _run_scenario_ablation(
    baseline_df: pd.DataFrame,
    eval_doc_ids: set[str],
    eval_path: Path,
    settings,
) -> list[dict]:
    """Measure each scenario with deterministic retrieval/F1 metrics only."""
    # Compute a like-for-like baseline with the same deterministic answerer;
    # main-run agent metrics must not be mixed into ablation deltas.
    ablation_baseline_index = LocalEmbeddingIndex.build(
        baseline_df,
        settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    ablation_baseline = evaluate_core_metrics(settings, ablation_baseline_index, eval_path)
    impacts: list[dict] = []
    for scenario in DEFAULT_SCENARIOS:
        scenario_df, operation = apply_corruption_scenario(
            baseline_df,
            scenario,
            eval_doc_ids=eval_doc_ids,
        )
        scenario_index = LocalEmbeddingIndex.build(
            scenario_df,
            settings,
            embeddings_output_path=settings.paths.corrupted_embeddings_json,
        )
        metrics = evaluate_core_metrics(settings, scenario_index, eval_path)
        baseline_retrieval = ablation_baseline.get("retrieval_hit_rate")
        baseline_f1 = ablation_baseline.get("mean_token_f1")
        impacts.append(
            {
                "scenario": scenario,
                "affected_eval_doc_ids": operation.get("affected_eval_doc_ids", []),
                "ablation_baseline_retrieval_hit_rate": baseline_retrieval,
                "ablation_baseline_mean_token_f1": baseline_f1,
                "retrieval_hit_rate": metrics["retrieval_hit_rate"],
                "retrieval_delta": (
                    metrics["retrieval_hit_rate"] - baseline_retrieval
                    if isinstance(baseline_retrieval, (int, float))
                    else None
                ),
                "mean_token_f1": metrics["mean_token_f1"],
                "token_f1_delta": (
                    metrics["mean_token_f1"] - baseline_f1
                    if isinstance(baseline_f1, (int, float))
                    else None
                ),
            }
        )
    return impacts


def repair_from_raw_snapshot(settings) -> pd.DataFrame:
    """Repair exclusively from the frozen raw-record artifact; never call the API."""
    raw_records = load_raw_records(settings.paths.raw_records_json)
    return build_clean_dataframe(raw_records, now_utc())

def main() -> None:
    """Run corruption, isolated re-evaluation, raw-source repair and comparison."""
    settings = load_settings()
    required_artifacts = [
        (settings.paths.clean_json, "baseline clean dataset"),
        (settings.paths.eval_testset, "evaluation set"),
        (settings.paths.baseline_metrics, "baseline metrics"),
        (settings.paths.raw_records_json, "raw records snapshot"),
        (Path(settings.paths.quality_dir) / "baseline.json", "baseline quality report"),
        (settings.paths.freshness_report, "baseline freshness report"),
    ]
    for path, description in required_artifacts:
        _require_artifact(path, description)

    baseline_df = pd.DataFrame(read_json(settings.paths.clean_json))
    validate_clean_dataframe(baseline_df, "baseline clean")
    paper_ids = set(baseline_df["paper_id"].astype(str))
    eval_path = Path(settings.paths.eval_testset)
    eval_payload = validate_evaluation_set(eval_path, paper_ids)
    eval_doc_ids = _evaluation_doc_ids(eval_payload)
    baseline_metrics = read_json(settings.paths.baseline_metrics)
    if not isinstance(baseline_metrics, dict):
        raise ValueError(f"Baseline metrics must be a JSON object: {settings.paths.baseline_metrics}")

    baseline_quality = read_json(Path(settings.paths.quality_dir) / "baseline.json")
    baseline_freshness = read_json(settings.paths.freshness_report)

    corrupted_df = corrupt_clean_dataframe(
        baseline_df,
        settings.paths.corruption_log,
        eval_doc_ids=eval_doc_ids,
        test_set_sha256=file_sha256(eval_path),
    )
    _save_dataframe(
        corrupted_df,
        settings.paths.corrupted_clean_csv,
        settings.paths.corrupted_clean_json,
        "corrupted clean",
    )
    # The experiment consumes the persisted artifact, enforcing the module
    # boundary between corruption and indexing.
    corrupted_df = _load_corrupted_csv(settings.paths.corrupted_clean_csv)

    scenario_impacts = _run_scenario_ablation(
        baseline_df,
        eval_doc_ids,
        eval_path,
        settings,
    )
    corruption_log = read_json(settings.paths.corruption_log)
    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    corrupted_bundle = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=eval_path,
        metrics_output_path=settings.paths.corrupted_metrics,
        answers_output_path=settings.paths.corrupted_answers,
        answerer=build_agent_answerer(settings, corrupted_index),
    )
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df,
        settings,
        _freshness_path(settings, "corrupted"),
    )

    repaired_df = repair_from_raw_snapshot(settings)
    validate_clean_dataframe(repaired_df, "repaired clean")
    validate_evaluation_set(eval_path, set(repaired_df["paper_id"].astype(str)))
    _save_dataframe(
        repaired_df,
        settings.paths.repaired_clean_csv,
        settings.paths.repaired_clean_json,
        "repaired clean",
    )
    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    repaired_bundle = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=eval_path,
        metrics_output_path=settings.paths.repaired_metrics,
        answers_output_path=settings.paths.repaired_answers,
        answerer=build_agent_answerer(settings, repaired_index),
    )
    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness = build_freshness_report(
        repaired_df,
        settings,
        _freshness_path(settings, "repaired"),
    )

    generate_corruption_report(
        report_path=settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_bundle.summary,
        repaired_metrics=repaired_bundle.summary,
        baseline_quality=baseline_quality,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        baseline_freshness=baseline_freshness,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
        corruption_log=corruption_log,
        scenario_impacts=scenario_impacts,
        repair_source=str(settings.paths.raw_records_json),
    )

    print(f"Corruption flow complete: baseline={len(baseline_df)}, corrupted={len(corrupted_df)}, repaired={len(repaired_df)}")
    print(f"Corruption log: {settings.paths.corruption_log}")
    print(f"Comparison report: {settings.paths.comparison_report}")
