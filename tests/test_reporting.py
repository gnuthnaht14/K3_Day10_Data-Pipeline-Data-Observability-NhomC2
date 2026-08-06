from __future__ import annotations

from pathlib import Path

from observability.reporting import generate_corruption_report


def _quality(status: str, failed: list[str]):
    return {
        "status": status,
        "passed": status == "pass",
        "total_rows": 3,
        "summary": {"failed_checks": len(failed), "failed_check_names": failed},
    }


def _freshness(status: str, stale: int):
    return {
        "status": status,
        "is_fresh": status == "fresh",
        "stale_rows": stale,
        "invalid_published_rows": 0,
        "total_rows": 3,
    }


def test_corruption_report_has_three_observability_states_and_missing_metrics(tmp_path: Path):
    report = tmp_path / "report.md"
    generate_corruption_report(
        report_path=report,
        baseline_metrics={"retrieval_hit_rate": 1.0, "optional_metric": 0.5},
        corrupted_metrics={"retrieval_hit_rate": 0.5},
        repaired_metrics={"retrieval_hit_rate": 1.0, "optional_metric": 0.5},
        baseline_quality=_quality("pass", []),
        corrupted_quality=_quality("fail", ["paper_id_unique"]),
        repaired_quality=_quality("pass", []),
        baseline_freshness=_freshness("fresh", 0),
        corrupted_freshness=_freshness("stale", 1),
        repaired_freshness=_freshness("fresh", 0),
        corruption_log={"affected_eval_doc_ids": ["doc-1"]},
        scenario_impacts=[
            {
                "scenario": "drop_eval_record",
                "affected_eval_doc_ids": ["doc-1"],
                "retrieval_hit_rate": 0.5,
                "retrieval_delta": -0.5,
                "mean_token_f1": 0.2,
                "token_f1_delta": -0.3,
            }
        ],
        repair_source="data/raw/crossref_records.json",
    )
    text = report.read_text(encoding="utf-8")
    assert "| Signal | Baseline | Corrupted | Repaired |" in text
    assert "paper_id_unique" in text
    assert "optional_metric" in text and "N/A" in text
    assert "Most severe retrieval scenario" in text
