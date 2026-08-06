from __future__ import annotations

from numbers import Number
from pathlib import Path
import json
from typing import Any

from core.utils import write_text


def _display(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(_display(value) for value in row) + " |" for row in rows)
    return lines


def _metric_rows(*metrics_payloads: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for payload in metrics_payloads:
        for key in payload:
            if key not in keys:
                keys.append(key)
    return keys


def _quality_lines(quality: dict[str, Any]) -> list[str]:
    summary = quality.get("summary", {}) if isinstance(quality, dict) else {}
    lines = [
        f"- Status: **{_display(quality.get('status'))}**",
        f"- Rows: **{_display(quality.get('total_rows'))}**",
        f"- Checks: **{_display(summary.get('passed_checks'))}/{_display(summary.get('total_checks'))} passed**",
    ]
    checks = quality.get("checks", []) if isinstance(quality, dict) else []
    if checks:
        lines.append("")
        lines.extend(_markdown_table(
            ["Check", "Value", "Threshold", "Passed"],
            [[check.get("name"), check.get("value"), check.get("threshold"), check.get("passed")] for check in checks],
        ))
    return lines


def _freshness_lines(freshness: dict[str, Any]) -> list[str]:
    rows = [
        ["Status", freshness.get("status")],
        ["Is fresh", freshness.get("is_fresh")],
        ["Latest published", freshness.get("latest_published")],
        ["Oldest published", freshness.get("oldest_published")],
        ["Stale rows", freshness.get("stale_rows")],
        ["Invalid published rows", freshness.get("invalid_published_rows")],
        ["Total rows", freshness.get("total_rows")],
        ["Threshold (days)", freshness.get("threshold_days")],
    ]
    return _markdown_table(["Field", "Value"], rows)


def _metric_value(payload: dict[str, Any], key: str) -> Any:
    value = payload.get(key)
    return value if isinstance(value, Number) and not isinstance(value, bool) else None


def _failed_check_names(quality: dict[str, Any]) -> list[str]:
    return list(quality.get("summary", {}).get("failed_check_names", []))


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Render a baseline report from source, metric and observability payloads."""
    lines = [
        "# Phase 1 Baseline Report",
        "",
        "## Source summary",
        "",
    ]
    lines.extend(_markdown_table(
        ["Field", "Value"],
        [[key, value] for key, value in source_summary.items()],
    ) if source_summary else ["No source summary was provided."])
    lines.extend(["", "## Evaluation metrics", ""])
    metric_rows = [[key, value] for key, value in metrics.items()]
    lines.extend(_markdown_table(["Metric", "Value"], metric_rows) if metric_rows else ["No evaluation metrics were provided."])
    lines.extend(["", "## Data quality", ""])
    lines.extend(_quality_lines(quality))
    lines.extend(["", "## Freshness", ""])
    lines.extend(_freshness_lines(freshness))
    lines.extend(
        [
            "",
            "## Metric interpretation",
            "",
            "- `retrieval_hit_rate` measures whether semantic retrieval places a ground-truth document in the top-k results. It evaluates the retriever/index, not the correctness of the final generated answer.",
            "- `exact_lookup_hit_rate` is reported separately and is never used to calculate semantic retrieval hit rate.",
            "- Token F1 can be below 1.0 even when retrieval finds the correct document because an answer may summarize, paraphrase, or use only part of the reference answer. Token F1 measures lexical overlap rather than semantic equivalence.",
            "- Answerer provenance: `" + _display(metrics.get("answerer_provenance")) + "`.",
            "- Judge provenance: `" + _display(metrics.get("judge_provenance")) + "`.",
            "- Ragas status: `" + _display(metrics.get("ragas")) + "`.",
        ]
    )
    write_text(Path(report_path), "\n".join(lines) + "\n")


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    baseline_quality: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    baseline_freshness: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    corruption_log: dict[str, Any] | None = None,
    scenario_impacts: list[dict[str, Any]] | None = None,
    repair_source: str | None = None,
) -> None:
    """Render a comparison report using the supplied baseline/corrupted/repaired payloads."""
    metric_keys = _metric_rows(baseline_metrics, corrupted_metrics, repaired_metrics)
    rows: list[list[Any]] = []
    for key in metric_keys:
        baseline = _metric_value(baseline_metrics, key)
        corrupted = _metric_value(corrupted_metrics, key)
        repaired = _metric_value(repaired_metrics, key)
        change = corrupted - baseline if baseline is not None and corrupted is not None else None
        recovery = repaired - corrupted if repaired is not None and corrupted is not None else None
        recovery_ratio = None
        recovery_status = "N/A"
        if key == "samples":
            recovery_status = "sample-count signal"
        elif baseline is not None and corrupted is not None and repaired is not None and corrupted < baseline:
            recovery_ratio = (repaired - corrupted) / (baseline - corrupted)
            recovery_status = "recovered" if repaired >= baseline else "partial recovery"
        elif baseline is not None and corrupted is not None and corrupted == baseline:
            recovery_status = "unchanged"
        elif baseline is not None and corrupted is not None and corrupted > baseline:
            recovery_status = "no observed degradation"
        rows.append([key, baseline, corrupted, repaired, change, recovery, recovery_ratio, recovery_status])

    lines = [
        "# Corruption and Repair Comparison Report",
        "",
        "## Evaluation metrics",
        "",
    ]
    lines.extend(_markdown_table(
        ["Metric", "Baseline", "Corrupted", "Repaired", "Corruption delta", "Recovery delta", "Recovery ratio", "Interpretation"],
        rows,
    ) if rows else ["No comparable metrics were provided."])
    lines.extend(["", "Recovery ratio = (repaired - corrupted) / (baseline - corrupted).", ""])

    lines.extend(["## Evaluation provenance", ""])
    provenance_rows = [
        ["Answerer", baseline_metrics.get("answerer_provenance"), corrupted_metrics.get("answerer_provenance"), repaired_metrics.get("answerer_provenance")],
        ["Judge", baseline_metrics.get("judge_provenance"), corrupted_metrics.get("judge_provenance"), repaired_metrics.get("judge_provenance")],
        ["Ragas", baseline_metrics.get("ragas"), corrupted_metrics.get("ragas"), repaired_metrics.get("ragas")],
    ]
    lines.extend(_markdown_table(["Component", "Baseline", "Corrupted", "Repaired"], provenance_rows))

    lines.extend(["", "## Data quality comparison", ""])
    quality_rows = [
        ["Status", baseline_quality.get("status"), corrupted_quality.get("status"), repaired_quality.get("status")],
        ["Passed", baseline_quality.get("passed"), corrupted_quality.get("passed"), repaired_quality.get("passed")],
        ["Total rows", baseline_quality.get("total_rows"), corrupted_quality.get("total_rows"), repaired_quality.get("total_rows")],
        ["Failed checks", _failed_check_names(baseline_quality), _failed_check_names(corrupted_quality), _failed_check_names(repaired_quality)],
    ]
    lines.extend(_markdown_table(["Signal", "Baseline", "Corrupted", "Repaired"], quality_rows))
    lines.extend(["", "## Freshness comparison", ""])
    freshness_rows = [
        ["Status", baseline_freshness.get("status"), corrupted_freshness.get("status"), repaired_freshness.get("status")],
        ["Is fresh", baseline_freshness.get("is_fresh"), corrupted_freshness.get("is_fresh"), repaired_freshness.get("is_fresh")],
        ["Stale rows", baseline_freshness.get("stale_rows"), corrupted_freshness.get("stale_rows"), repaired_freshness.get("stale_rows")],
        ["Invalid published rows", baseline_freshness.get("invalid_published_rows"), corrupted_freshness.get("invalid_published_rows"), repaired_freshness.get("invalid_published_rows")],
        ["Total rows", baseline_freshness.get("total_rows"), corrupted_freshness.get("total_rows"), repaired_freshness.get("total_rows")],
    ]
    lines.extend(_markdown_table(["Signal", "Baseline", "Corrupted", "Repaired"], freshness_rows))

    impacts = scenario_impacts or []
    lines.extend(["", "## Per-scenario impact (ablation)", ""])
    lines.append("Ablation deltas use the same deterministic answerer for their own baseline and every isolated scenario; they are not compared with the main LLM-agent Token F1.")
    lines.append("")
    impact_rows = [
        [
            item.get("scenario"),
            item.get("affected_eval_doc_ids"),
            item.get("retrieval_hit_rate"),
            item.get("retrieval_delta"),
            item.get("mean_token_f1"),
            item.get("token_f1_delta"),
        ]
        for item in impacts
    ]
    lines.extend(
        _markdown_table(
            ["Scenario", "Affected eval IDs", "Retrieval hit", "Retrieval delta", "Token F1", "Token F1 delta"],
            impact_rows,
        )
        if impact_rows
        else ["No per-scenario metrics were provided."]
    )

    comparable = [item for item in impacts if isinstance(item.get("retrieval_delta"), Number)]
    most_severe = min(
        comparable,
        key=lambda item: (item.get("retrieval_delta", 0), item.get("token_f1_delta", 0)),
    ) if comparable else None
    lines.extend(["", "## Checkpoint interpretation", ""])
    if most_severe is not None:
        lines.append(
            "- Most severe retrieval scenario: `"
            + _display(most_severe.get("scenario"))
            + "` with retrieval delta `"
            + _display(most_severe.get("retrieval_delta"))
            + "`, measured independently by ablation."
        )
    overlap = (corruption_log or {}).get("affected_eval_doc_ids", [])
    lines.append("- Frozen-test overlap IDs: `" + _display(overlap) + "`.")
    lines.append(
        "- Repair source: `"
        + _display(repair_source)
        + "`. Repair rebuilds clean data from the saved raw snapshot instead of fetching Crossref again because the API result and metadata may change over time; the snapshot keeps the experiment reproducible and isolates the effect of corruption."
    )
    write_text(Path(report_path), "\n".join(lines) + "\n")
