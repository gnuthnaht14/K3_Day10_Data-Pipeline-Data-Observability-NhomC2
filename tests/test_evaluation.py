from __future__ import annotations

from pathlib import Path

from core.config import load_settings
from core.utils import read_json, write_json
from evaluation.metrics import _judge_answer, evaluate_pipeline
from retrieval.index import SearchResult
from retrieval.qa import answer_question


class FakeIndex:
    def __init__(self):
        self.semantic = SearchResult(
            paper_id="wrong-doc",
            title="A different paper",
            score=0.9,
            content="A different paper. Authors: Someone Else. Published: 2020-01-01",
            metadata={
                "paper_id": "wrong-doc",
                "title": "A different paper",
                "summary": "Unrelated summary.",
                "authors_joined": "Someone Else",
                "categories_joined": "",
                "published": "2020-01-01",
            },
        )
        self.exact = {
            "paper_id": "target-doc",
            "title": "Target Paper",
            "content": "Target Paper. Authors: Alice, Bob. Published: 2026-01-02",
            "metadata": {
                "paper_id": "target-doc",
                "title": "Target Paper",
                "summary": "This is the target summary.",
                "authors_joined": "Alice, Bob",
                "categories_joined": "",
                "published": "2026-01-02",
            },
        }

    def search(self, query: str, top_k=None):
        return [self.semantic]

    def lookup(self, value: str):
        return self.exact if value == "Target Paper" else None


def test_semantic_trace_is_not_replaced_by_exact_lookup(tmp_path: Path):
    settings = load_settings(tmp_path)
    result = answer_question(
        "Who are the authors of the paper 'Target Paper'?",
        settings,
        FakeIndex(),
    )
    assert result.answer == "Alice, Bob"
    assert result.retrieved_doc_ids == ["wrong-doc"]
    assert result.exact_lookup_hit is True


def test_pipeline_retrieval_metric_uses_semantic_results(tmp_path: Path):
    settings = load_settings(tmp_path)
    test_set_path = tmp_path / "data" / "eval" / "test_set.json"
    metrics_path = tmp_path / "data" / "results" / "metrics.json"
    answers_path = tmp_path / "data" / "results" / "answers.json"
    write_json(
        test_set_path,
        [
            {
                "id": "q-001",
                "question_type": "date",
                "question": "When was the paper 'Target Paper' published?",
                "ground_truth": "2026-01-02",
                "ground_truth_doc_ids": ["target-doc"],
            }
        ],
    )
    bundle = evaluate_pipeline(settings, FakeIndex(), test_set_path, metrics_path, answers_path)
    assert bundle.summary["retrieval_hit_rate"] == 0.0
    assert bundle.summary["exact_lookup_hit_rate"] == 1.0
    assert read_json(answers_path)[0]["retrieved_doc_ids"] == ["wrong-doc"]


def test_empty_answer_judge_is_deterministic_and_does_not_call_llm(tmp_path: Path):
    settings = load_settings(tmp_path)
    verdict = _judge_answer(settings, "summary", "Question", "Reference", "   ")
    assert verdict.correct is False
    assert verdict.score == 1
    assert verdict.mode == "empty_answer_guard"


def test_structured_field_judge_accepts_answer_prose(tmp_path: Path):
    settings = load_settings(tmp_path)
    verdict = _judge_answer(
        settings,
        "authors",
        "Who are the authors?",
        "Alice, Bob",
        "The authors are Alice and Bob.",
    )
    assert verdict.correct is True
    assert verdict.mode == "deterministic_authors"
