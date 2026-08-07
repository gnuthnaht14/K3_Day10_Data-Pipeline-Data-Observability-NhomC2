from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.utils import write_text


_METRIC_LABELS = {
    "samples": "Evaluation samples",
    "retrieval_hit_rate": "Retrieval hit rate",
    "mean_token_f1": "Mean token F1",
    "judge_accuracy": "Judge accuracy",
    "mean_judge_score": "Mean judge score",
}


def _markdown_cell(value: Any) -> str:
    """Render arbitrary artifact values safely inside a Markdown table cell."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, (list, tuple)):
        return ", ".join(_markdown_cell(item) for item in value) or "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _metric_value(metrics: dict[str, Any], key: str) -> str:
    return _markdown_cell(metrics.get(key))


def _status(value: Any) -> str:
    if value is True or value == "passed":
        return "PASS"
    if value is False or value == "failed":
        return "FAIL"
    return "N/A"


def _quality_rows(quality: dict[str, Any]) -> list[str]:
    checks = quality.get("checks", [])
    if not checks:
        return [
            "| Check | Status | Failed rows | Expected |",
            "| --- | --- | ---: | --- |",
            f"| Overall quality | {_status(quality.get('status'))} | — | "
            f"{_markdown_cell(quality.get('failed_checks'))} |",
        ]
    return [
        "| Check | Status | Failed rows | Expected |",
        "| --- | --- | ---: | --- |",
        *[
            "| {name} | {status} | {failed_rows} | {expected} |".format(
                name=_markdown_cell(check.get("name")),
                status=_status(check.get("status")),
                failed_rows=_markdown_cell(check.get("failed_rows")),
                expected=_markdown_cell(check.get("expected")),
            )
            for check in checks
        ],
    ]


def _freshness_rows(freshness: dict[str, Any]) -> list[str]:
    keys = (
        "status",
        "is_fresh",
        "threshold_days",
        "latest_published",
        "oldest_published",
        "stale_rows",
        "invalid_published_rows",
        "total_rows",
    )
    return [
        "| Freshness field | Value |",
        "| --- | --- |",
        *[
            f"| {key.replace('_', ' ').title()} | {_markdown_cell(freshness.get(key))} |"
            for key in keys
            if key in freshness
        ],
    ]


def _numeric_metric(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _delta(current: dict[str, Any], baseline: dict[str, Any], key: str) -> str:
    current_value = _numeric_metric(current, key)
    baseline_value = _numeric_metric(baseline, key)
    if current_value is None or baseline_value is None:
        return "—"
    difference = current_value - baseline_value
    if key in {"retrieval_hit_rate", "mean_token_f1", "judge_accuracy"}:
        return f"{difference * 100:+.2f} pp"
    return f"{difference:+.4f}"


def _metric_analysis(
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
) -> list[str]:
    """Generate evidence-based observations; never claim a change without values."""
    observations: list[str] = []
    for key, label in _METRIC_LABELS.items():
        if key == "samples":
            continue
        baseline = _numeric_metric(baseline_metrics, key)
        corrupted = _numeric_metric(corrupted_metrics, key)
        repaired = _numeric_metric(repaired_metrics, key)
        if baseline is not None and corrupted is not None:
            direction = "decreased" if corrupted < baseline else "increased" if corrupted > baseline else "did not change"
            observations.append(f"{label} {direction} by {_delta(corrupted_metrics, baseline_metrics, key)} after corruption.")
        if baseline is not None and repaired is not None:
            direction = "is below" if repaired < baseline else "is above" if repaired > baseline else "matches"
            observations.append(f"Repaired {label.lower()} {direction} the baseline by {_delta(repaired_metrics, baseline_metrics, key)}.")
    return observations or ["Metrics were unavailable, so no metric trend can be inferred."]

def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """TODO(student): viet markdown report cho baseline phase.

    Pseudo-code:
    1. Gom source summary.
    2. In metrics retrieval/evaluation.
    3. In data quality va freshness.
    4. Ghi markdown vao report_path.
    """
    source_rows = [
        f"| {_markdown_cell(key)} | {_markdown_cell(value)} |"
        for key, value in source_summary.items()
    ] or ["| Source summary | No source metadata supplied |"]
    metric_rows = [
        f"| {label} | {_metric_value(metrics, key)} |"
        for key, label in _METRIC_LABELS.items()
        if key in metrics
    ] or ["| Metrics | No evaluation metrics supplied |"]
    ragas = metrics.get("ragas")
    ragas_note = "—" if ragas is None else _markdown_cell(ragas)

    lines = [
        "# Phase 1 Baseline Data Observability Report",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## Source snapshot",
        "",
        "| Field | Value |",
        "| --- | --- |",
        *source_rows,
        "",
        "## RAG evaluation",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        *metric_rows,
        "",
        f"Ragas: {ragas_note}",
        "",
        "## Data quality",
        "",
        f"Overall status: **{_status(quality.get('status'))}**. "
        f"Passed checks: {_markdown_cell(quality.get('passed_checks'))}; "
        f"failed checks: {_markdown_cell(quality.get('failed_checks'))}.",
        "",
        *_quality_rows(quality),
        "",
        "## Freshness",
        "",
        f"Freshness status: **{_status(freshness.get('status', freshness.get('is_fresh')))}**.",
        "",
        *_freshness_rows(freshness),
        "",
        "## Interpretation",
        "",
        "This report is a baseline snapshot. Later corruption and repair runs should use the same evaluation set so metric changes can be attributed to the dataset state.",
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))


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
    """TODO(student): viet markdown report so sanh baseline/corrupted/repaired."""
    metric_keys = [key for key in _METRIC_LABELS if any(key in payload for payload in (baseline_metrics, corrupted_metrics, repaired_metrics))]
    metric_rows = [
        "| Metric | Baseline | Corrupted | Δ corrupted vs baseline | Repaired | Δ repaired vs baseline |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        *[
            "| {label} | {baseline} | {corrupted} | {corrupted_delta} | {repaired} | {repaired_delta} |".format(
                label=label,
                baseline=_metric_value(baseline_metrics, key),
                corrupted=_metric_value(corrupted_metrics, key),
                corrupted_delta=_delta(corrupted_metrics, baseline_metrics, key),
                repaired=_metric_value(repaired_metrics, key),
                repaired_delta=_delta(repaired_metrics, baseline_metrics, key),
            )
            for key, label in _METRIC_LABELS.items()
            if key in metric_keys
        ],
    ]
    quality_rows = [
        "| Dataset state | Quality status | Failed checks |",
        "| --- | --- | --- |",
        f"| Corrupted | {_status(corrupted_quality.get('status'))} | {_markdown_cell(corrupted_quality.get('failed_checks'))} |",
        f"| Repaired | {_status(repaired_quality.get('status'))} | {_markdown_cell(repaired_quality.get('failed_checks'))} |",
    ]
    freshness_rows = [
        "| Dataset state | Freshness status | Stale rows | Invalid dates | Latest published | Oldest published |",
        "| --- | --- | ---: | ---: | --- | --- |",
        "| Corrupted | {status} | {stale} | {invalid} | {latest} | {oldest} |".format(
            status=_status(corrupted_freshness.get("status", corrupted_freshness.get("is_fresh"))),
            stale=_markdown_cell(corrupted_freshness.get("stale_rows")),
            invalid=_markdown_cell(corrupted_freshness.get("invalid_published_rows")),
            latest=_markdown_cell(corrupted_freshness.get("latest_published")),
            oldest=_markdown_cell(corrupted_freshness.get("oldest_published")),
        ),
        "| Repaired | {status} | {stale} | {invalid} | {latest} | {oldest} |".format(
            status=_status(repaired_freshness.get("status", repaired_freshness.get("is_fresh"))),
            stale=_markdown_cell(repaired_freshness.get("stale_rows")),
            invalid=_markdown_cell(repaired_freshness.get("invalid_published_rows")),
            latest=_markdown_cell(repaired_freshness.get("latest_published")),
            oldest=_markdown_cell(repaired_freshness.get("oldest_published")),
        ),
    ]
    lines = [
        "# Corruption and Repair Observability Report",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## Evaluation comparison",
        "",
        *metric_rows,
        "",
        "## Data quality comparison",
        "",
        *quality_rows,
        "",
        "## Freshness comparison",
        "",
        *freshness_rows,
        "",
        "## Metric analysis",
        "",
        *[f"- {observation}" for observation in _metric_analysis(baseline_metrics, corrupted_metrics, repaired_metrics)],
        "",
        "## Conclusion",
        "",
        "Compare the quality/freshness failures with the metric deltas above. A repaired dataset is successful when it clears the relevant checks and moves evaluation metrics back toward the baseline.",
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))
