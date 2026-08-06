from __future__ import annotations

from typing import Any
from pathlib import Path

import pandas as pd

from core.utils import write_json


EVALUATION_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "published",
    "authors_joined",
    "categories_joined",
]
QUESTION_TYPES = ("summary", "authors", "date", "categories")
MAX_DOCUMENTS_PER_TYPE = 3


def _value(row: pd.Series, column: str) -> str:
    value = row.get(column, "")
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _question(question_type: str, title: str) -> str:
    prompts = {
        "summary": f"What is the main contribution or summary of the paper '{title}'?",
        "authors": f"Who are the authors of the paper '{title}'?",
        "date": f"When was the paper '{title}' published?",
        "categories": f"What subject categories describe the paper '{title}'?",
    }
    return prompts[question_type]


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Create a deterministic evaluation set from a validated Clean Schema."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")
    missing = [column for column in EVALUATION_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Clean dataframe is missing required columns: {', '.join(missing)}")
    if df.empty:
        raise ValueError("At least one clean document is required to build an evaluation set.")

    clean = df.copy()
    ids = clean["paper_id"].fillna("").astype(str).str.strip()
    if ids.eq("").any() or ids.duplicated().any():
        raise ValueError("Clean dataframe must contain unique, non-empty paper_id values.")
    clean["paper_id"] = ids
    clean["title"] = clean["title"].fillna("").astype(str).str.strip()
    if clean["title"].eq("").any():
        raise ValueError("Clean dataframe must contain non-empty titles.")
    clean = clean.sort_values(["paper_id", "title"], kind="mergesort").reset_index(drop=True)

    items: list[dict[str, Any]] = []
    item_number = 1
    for question_type in QUESTION_TYPES:
        ground_truth_column = {
            "summary": "summary",
            "authors": "authors_joined",
            "date": "published",
            "categories": "categories_joined",
        }[question_type]
        values = clean[ground_truth_column].fillna("").astype(str).str.strip()
        # A missing category is itself a valid, auditable answer.  Keeping a
        # category question makes the evaluation schema stable even when the
        # source does not provide subject metadata.
        if question_type == "categories":
            eligible = clean
        else:
            eligible = clean[values.ne("")]
        for _, row in eligible.head(MAX_DOCUMENTS_PER_TYPE).iterrows():
            paper_id = _value(row, "paper_id")
            title = _value(row, "title")
            ground_truth = _value(row, ground_truth_column)
            if question_type == "categories" and not ground_truth:
                ground_truth = "No subject categories are listed in the clean record."
            items.append(
                {
                    "id": f"q-{item_number:03d}",
                    "question_type": question_type,
                    "question": _question(question_type, title),
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": [paper_id],
                }
            )
            item_number += 1

    if not items:
        raise ValueError("No eligible clean documents contain fields needed for evaluation.")

    valid_ids = set(clean["paper_id"])
    invalid_doc_ids = {
        doc_id
        for item in items
        for doc_id in item["ground_truth_doc_ids"]
        if doc_id not in valid_ids
    }
    if invalid_doc_ids:
        raise ValueError(f"Evaluation set contains unknown document IDs: {sorted(invalid_doc_ids)}")

    write_json(Path(output_path), items)
    return items
