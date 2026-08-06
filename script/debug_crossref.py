"""
Script debug thu cong cho crossref.py - goi API Crossref THAT (can internet).
Dat file nay o thu muc scripts/ (ngang hang voi src/), KHONG dat trong src/ingestion/
de tranh loi RuntimeWarning ve module bi import 2 lan.

Chay tu thu muc goc project (noi co pyproject.toml va .env):
    python scripts/debug_crossref.py
hoac:
    uv run python scripts/debug_crossref.py
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

# Neu chua "pip install -e ." / "uv sync" thi can them src/ vao sys.path thu cong
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from core.config import load_settings  # noqa: E402
from ingestion.crossref import fetch_source_records, load_raw_records  # noqa: E402


def main() -> None:
    print("=" * 60)
    print("DEBUG: goi Crossref API that...")
    print("=" * 60)

    # load_settings() tu doc .env va tu tinh het duong dan, KHONG can tu tao Paths
    settings = load_settings()

    # Settings la frozen dataclass -> khong gan truc tiep duoc, dung dataclasses.replace
    # De debug nhanh, chi lay 5 bai thay vi 24 bai mac dinh
    settings = dataclasses.replace(settings, max_results=24)

    print(f"source_query  : {settings.source_query}")
    print(f"source_filter : {settings.source_filter}")
    print(f"max_results   : {settings.max_results}")
    print()

    records = fetch_source_records(settings)

    print(f"\n>>> Lay duoc {len(records)} record hop le (co du DOI + title + abstract)\n")

    for i, r in enumerate(records, start=1):
        print(f"--- Record {i} ---")
        print(f"  paper_id     : {r.paper_id}")
        print(f"  title        : {r.title[:80]}")
        print(f"  authors      : {r.authors}")
        print(f"  categories   : {r.categories}")
        print(f"  published    : {r.published}")
        print(f"  updated      : {r.updated}")
        print(f"  pdf_url      : {r.pdf_url or '(khong co)'}")
        print(f"  summary(80c) : {r.summary[:80]}...")
        print()

    print("=" * 60)
    print("Kiem tra file da luu:")
    print(f"  - {settings.paths.raw_api_response}")
    print(f"  - {settings.paths.raw_records_json}")
    print("=" * 60)

    # Test luon load_raw_records de chac chan roundtrip khong loi
    reloaded = load_raw_records(settings.paths.raw_records_json)
    assert len(reloaded) == len(records), "So luong record sau khi load lai bi lech!"
    print(f"\n>>> load_raw_records() doc lai thanh cong {len(reloaded)} record. OK.")


if __name__ == "__main__":
    main()