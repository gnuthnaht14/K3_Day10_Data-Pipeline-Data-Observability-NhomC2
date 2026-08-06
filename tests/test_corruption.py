from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pandas.testing as pdt

from core.config import load_settings
from core.utils import read_json
from ingestion.cleaning import CLEAN_COLUMNS
from ingestion.corruption import CORRUPTION_MARKER, corrupt_clean_dataframe
from observability.quality import run_data_quality_checks


def _clean_frame() -> pd.DataFrame:
    today = datetime.now(UTC).date().isoformat()
    rows = []
    for number in range(1, 4):
        rows.append(
            {
                "paper_id": f"doc-{number}",
                "title": f"Paper {number}",
                "summary": f"A sufficiently long clean summary for paper number {number}.",
                "published": today,
                "authors_joined": f"Author {number}",
                "categories_joined": "AI",
                "age_days": 0,
                "text_for_embedding": f"Paper {number} clean searchable content",
                "abs_url": f"https://example.test/{number}",
                "pdf_url": "",
            }
        )
    return pd.DataFrame(rows)[CLEAN_COLUMNS]


def test_corruption_is_deterministic_overlaps_eval_and_fails_quality(tmp_path: Path):
    settings = load_settings(tmp_path)
    clean = _clean_frame()
    first_log = tmp_path / "first.json"
    second_log = tmp_path / "second.json"
    first = corrupt_clean_dataframe(clean, first_log, eval_doc_ids={"doc-1", "doc-2", "doc-3"})
    second = corrupt_clean_dataframe(clean, second_log, eval_doc_ids={"doc-1", "doc-2", "doc-3"})

    pdt.assert_frame_equal(first, second)
    log = read_json(first_log)
    assert log["overlap_with_eval"] is True
    assert log["affected_eval_doc_ids"]
    assert all(operation["overlap_with_eval"] for operation in log["operations"])
    assert first["text_for_embedding"].str.contains(CORRUPTION_MARKER, regex=False).any()

    quality = run_data_quality_checks(first, settings, "corrupted-test")
    assert quality["status"] == "fail"
    assert {"paper_id_unique", "summary_min_length", "stale_rows"}.issubset(
        quality["summary"]["failed_check_names"]
    )
