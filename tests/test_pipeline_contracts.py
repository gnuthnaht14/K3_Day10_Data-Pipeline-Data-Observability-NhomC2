from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from core.config import load_settings
from core.utils import file_sha256, write_json
from ingestion.cleaning import CLEAN_COLUMNS
from pipelines.corruption_flow import repair_from_raw_snapshot
from pipelines.phase1 import load_or_build_evaluation_set


def _one_clean_row() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "paper_id": "doc-1",
                "title": "Frozen Paper",
                "summary": "A sufficiently long summary for the frozen paper.",
                "published": datetime.now(UTC).date().isoformat(),
                "authors_joined": "Alice",
                "categories_joined": "AI",
                "age_days": 0,
                "text_for_embedding": "Frozen Paper and its searchable content",
                "abs_url": "https://example.test/doc-1",
                "pdf_url": "",
            }
        ]
    )[CLEAN_COLUMNS]


def test_existing_test_set_stays_frozen(tmp_path: Path):
    settings = replace(load_settings(tmp_path), refresh_test_set=False)
    payload = [
        {
            "id": "q-001",
            "question_type": "date",
            "question": "When was the paper 'Frozen Paper' published?",
            "ground_truth": datetime.now(UTC).date().isoformat(),
            "ground_truth_doc_ids": ["doc-1"],
        }
    ]
    write_json(settings.paths.eval_testset, payload)
    before = file_sha256(settings.paths.eval_testset)
    loaded = load_or_build_evaluation_set(settings, _one_clean_row())
    assert loaded == payload
    assert file_sha256(settings.paths.eval_testset) == before


def test_repair_uses_saved_raw_snapshot_without_network(tmp_path: Path, monkeypatch):
    settings = load_settings(tmp_path)
    write_json(
        settings.paths.raw_records_json,
        [
            {
                "paper_id": "doc-1",
                "title": "Raw Snapshot Paper",
                "summary": "A sufficiently long summary restored from the raw snapshot.",
                "authors": ["Alice"],
                "categories": ["AI"],
                "primary_category": "AI",
                "published": datetime.now(UTC).date().isoformat(),
                "updated": "",
                "abs_url": "https://example.test/doc-1",
                "pdf_url": "",
                "comment": "",
            }
        ],
    )

    def fail_network(*args, **kwargs):
        raise AssertionError("Repair must not call the network")

    monkeypatch.setattr("ingestion.crossref.requests.get", fail_network)
    repaired = repair_from_raw_snapshot(settings)
    assert repaired["paper_id"].tolist() == ["doc-1"]
    assert repaired["paper_id"].is_unique
