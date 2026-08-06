"""
Chay: pytest tests/test_crossref.py -v
Khong goi API that - dung unittest.mock de gia lap requests.get.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from dataclasses import replace
from core.config import load_settings
from pathlib import Path

from core.config import Paths, Settings
from ingestion.crossref import (
    PaperRecord,
    fetch_source_records,
    load_raw_records,
    parse_crossref_payload,
)


# ---------------------------------------------------------------------------
# Fixture: payload mo phong response that cua Crossref
# ---------------------------------------------------------------------------

def make_payload(items: list[dict]) -> dict:
    return {"status": "ok", "message-type": "work-list", "message": {"items": items}}


VALID_ITEM = {
    "DOI": "10.1000/valid-doi",
    "title": ["Deep Learning for <b>Machine</b> Translation"],
    "abstract": "<jats:p>This paper explores deep learning models for translation tasks.</jats:p>",
    "author": [{"given": "An", "family": "Nguyen"}, {"given": "Bao", "family": "Tran"}],
    "subject": ["Computer Science", "Machine Learning"],
    "published-print": {"date-parts": [[2023, 5, 12]]},
    "indexed": {"date-time": "2023-05-20T10:00:00Z"},
    "URL": "https://doi.org/10.1000/valid-doi",
    "link": [{"URL": "https://example.com/paper.pdf", "content-type": "application/pdf"}],
    "container-title": ["Journal of AI Research"],
}

MISSING_ABSTRACT_ITEM = {
    "DOI": "10.1000/no-abstract",
    "title": ["Paper Without Abstract"],
    # khong co field "abstract"
}

MISSING_TITLE_ITEM = {
    "DOI": "10.1000/no-title",
    "title": [],
    "abstract": "Has an abstract but no title.",
}

ORG_AUTHOR_ITEM = {
    "DOI": "10.1000/org-author",
    "title": ["Report from an Organization"],
    "abstract": "Some organizations publish without individual named authors.",
    "author": [{"name": "World Health Organization"}],
    "issued": {"date-parts": [[2022]]},
}


# ---------------------------------------------------------------------------
# Tests: parse_crossref_payload (khong can mock, chi test logic parse)
# ---------------------------------------------------------------------------

class TestParseCrossrefPayload:
    def test_valid_item_parsed_correctly(self):
        records = parse_crossref_payload(make_payload([VALID_ITEM]))
        assert len(records) == 1
        r = records[0]
        assert r.paper_id == "10.1000/valid-doi"
        assert r.title == "Deep Learning for <b>Machine</b> Translation"  # tag chua bi strip o day
        assert "<jats:p>" in r.summary  # crossref.py KHONG bi tag, do la viec cua cleaning.py
        assert r.authors == ["An Nguyen", "Bao Tran"]
        assert r.categories == ["Computer Science", "Machine Learning"]
        assert r.primary_category == "Computer Science"
        assert r.published == "2023-05-12"
        assert r.updated == "2023-05-20T10:00:00Z"
        assert r.pdf_url == "https://example.com/paper.pdf"
        assert r.comment == "Journal of AI Research"

    def test_missing_abstract_is_dropped(self):
        records = parse_crossref_payload(make_payload([MISSING_ABSTRACT_ITEM]))
        assert records == []

    def test_missing_title_is_dropped(self):
        records = parse_crossref_payload(make_payload([MISSING_TITLE_ITEM]))
        assert records == []

    def test_organization_author_uses_name_field(self):
        records = parse_crossref_payload(make_payload([ORG_AUTHOR_ITEM]))
        assert len(records) == 1
        assert records[0].authors == ["World Health Organization"]
        assert records[0].published == "2022-01-01"  # chi co year -> fill thang/ngay = 01

    def test_mixed_valid_and_invalid_items(self):
        records = parse_crossref_payload(
            make_payload([VALID_ITEM, MISSING_ABSTRACT_ITEM, MISSING_TITLE_ITEM])
        )
        assert len(records) == 1
        assert records[0].paper_id == "10.1000/valid-doi"

    def test_empty_items_list(self):
        assert parse_crossref_payload(make_payload([])) == []


# ---------------------------------------------------------------------------
# Tests: retry/backoff logic (mock requests.get)
# ---------------------------------------------------------------------------

class TestRetryLogic:
    @patch("ingestion.crossref.time.sleep", return_value=None)  # bo qua thoi gian cho that
    @patch("ingestion.crossref.requests.get")
    def test_retries_on_429_then_succeeds(self, mock_get, mock_sleep):
        rate_limited = MagicMock(status_code=429, headers={})
        success = MagicMock(status_code=200, headers={})
        success.json.return_value = make_payload([VALID_ITEM])
        success.raise_for_status.return_value = None
        mock_get.side_effect = [rate_limited, success]

        settings = load_settings()

        settings = replace(
            settings,
            paths=replace(
                settings.paths,
                raw_api_response=Path("out/response.json"),
                raw_records_json=Path("out/records.json"),
            ),
        )

        import os
        os.chdir("/tmp")
        records = fetch_source_records(settings)

        assert mock_get.call_count == 2
        assert len(records) == 1

    @patch("ingestion.crossref.time.sleep", return_value=None)
    @patch("ingestion.crossref.requests.get")
    def test_gives_up_after_max_retries(self, mock_get, mock_sleep):
        always_503 = MagicMock(status_code=503, headers={})
        mock_get.return_value = always_503

        settings = load_settings()

        with pytest.raises(RuntimeError):
            fetch_source_records(settings)


# ---------------------------------------------------------------------------
# Tests: file I/O (raw artifacts + load_raw_records roundtrip)
# ---------------------------------------------------------------------------

class TestFileArtifacts:
    @patch("ingestion.crossref.requests.get")
    def test_fetch_saves_both_raw_files(self, mock_get, tmp_path):
        resp = MagicMock(status_code=200, headers={})
        resp.json.return_value = make_payload([VALID_ITEM])
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp

        response_path = tmp_path / "raw" / "crossref_response.json"
        records_path = tmp_path / "raw" / "crossref_records.json"
        settings = load_settings()

        settings = replace(
            settings,
            paths=replace(
                settings.paths,
                raw_api_response=response_path,
                raw_records_json=records_path,
            ),
        )

        records = fetch_source_records(settings)

        assert response_path.exists()
        assert records_path.exists()

        saved_response = json.loads(response_path.read_text())
        assert saved_response["message"]["items"][0]["DOI"] == "10.1000/valid-doi"

        saved_records = json.loads(records_path.read_text())
        assert saved_records[0]["paper_id"] == "10.1000/valid-doi"
        assert len(records) == 1

    def test_load_raw_records_roundtrip(self, tmp_path):
        original = [
            PaperRecord(
                paper_id="10.1000/x", title="T", summary="S", authors=["A"],
                categories=["C"], primary_category="C", published="2023-01-01",
                updated="2023-01-02T00:00:00Z", abs_url="https://x", pdf_url="",
                comment="Journal X",
            )
        ]
        path = tmp_path / "records.json"
        path.write_text(json.dumps([r.__dict__ for r in original]))

        loaded = load_raw_records(path)
        assert loaded == original


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))