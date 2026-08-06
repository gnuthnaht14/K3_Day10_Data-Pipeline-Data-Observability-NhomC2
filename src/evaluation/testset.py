from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Create factual evaluation questions whose answers come from clean data."""
    required_columns = {
        "paper_id",
        "title",
        "summary",
        "published",
        "authors_joined",
    }
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(f"Clean dataframe is missing columns: {sorted(missing_columns)}")
    if len(df) < 5:
        raise ValueError("At least 5 clean documents are required to build the test set.")

    samples: list[dict[str, Any]] = []

    def add_sample(question_type: str, question: str, answer: Any, paper_id: Any) -> None:
        samples.append(
            {
                "id": f"q{len(samples) + 1}",
                "question_type": question_type,
                "question": question,
                "ground_truth": str(answer),
                "ground_truth_doc_ids": [str(paper_id)],
            }
        )

    # Two direct, reproducible questions per document gives 10 samples for the
    # current corpus and remains deterministic if the clean data is regenerated.
    for index, row in enumerate(df.head(5).to_dict(orient="records")):
        paper_id = row["paper_id"]
        title = str(row["title"])
        authors = str(row["authors_joined"])
        published = str(row["published"])
        summary = str(row["summary"])

        add_sample(
            "factual",
            f"Tiêu đề của bài báo có paper_id {paper_id} là gì?",
            title,
            paper_id,
        )
        if index % 2 == 0:
            add_sample(
                "authors",
                f"Ai là tác giả của bài báo '{title}'?",
                authors,
                paper_id,
            )
        else:
            add_sample(
                "date",
                f"Bài báo '{title}' được xuất bản vào ngày nào?",
                published,
                paper_id,
            )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    return samples
