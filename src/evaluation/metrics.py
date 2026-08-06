from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
import os
import sys
import types
from typing import Any, Callable

from datasets import Dataset
from pydantic import BaseModel, Field

from core.config import Settings, normalized_provider
from core.utils import normalize_whitespace, read_json, write_json
from retrieval.embeddings import MiniLMEmbeddings
from retrieval.index import LocalEmbeddingIndex
from retrieval.llm import build_llm
from retrieval.qa import AnswerResult, answer_question


class JudgeVerdict(BaseModel):
    score: int = Field(ge=1, le=5)
    correct: bool
    reasoning: str
    mode: str
    provider: str
    model: str
    fallback_used: bool = False
    error: str | None = None


class LLMJudgeDecision(BaseModel):
    score: int = Field(ge=1, le=5)
    correct: bool
    reasoning: str


@dataclass(frozen=True)
class EvaluationBundle:
    summary: dict[str, Any]
    answers: list[dict[str, Any]]


def _token_f1(reference: str, prediction: str) -> float:
    ref_tokens = normalize_whitespace(reference).lower().split()
    pred_tokens = normalize_whitespace(prediction).lower().split()
    if not ref_tokens or not pred_tokens:
        return 0.0
    ref_set = set(ref_tokens)
    pred_set = set(pred_tokens)
    overlap = len(ref_set & pred_set)
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_set)
    recall = overlap / len(ref_set)
    return 2 * precision * recall / (precision + recall)


def _normalized_exact(value: str) -> str:
    return normalize_whitespace(value).casefold().strip(" .")


def _structured_field_correct(question_type: str, reference: str, prediction: str) -> bool:
    normalized_reference = _normalized_exact(reference)
    normalized_prediction = _normalized_exact(prediction)
    if question_type == "date":
        return normalized_reference in normalized_prediction
    if question_type == "authors":
        names = [_normalized_exact(name) for name in reference.split(",") if name.strip()]
        return bool(names) and all(name in normalized_prediction for name in names)
    return normalized_reference == normalized_prediction or normalized_reference in normalized_prediction


def _judge_answer(
    settings: Settings,
    question_type: str,
    question: str,
    reference: str,
    prediction: str,
) -> JudgeVerdict:
    provider = normalized_provider(settings)
    if not normalize_whitespace(prediction):
        return JudgeVerdict(
            score=1,
            correct=False,
            reasoning="The model answer is empty.",
            mode="empty_answer_guard",
            provider=provider,
            model=settings.model_name,
        )

    if question_type in {"authors", "date", "categories"}:
        correct = _structured_field_correct(question_type, reference, prediction)
        return JudgeVerdict(
            score=5 if correct else 1,
            correct=correct,
            reasoning=f"Deterministic normalized comparison for {question_type}.",
            mode=f"deterministic_{question_type}",
            provider=provider,
            model=settings.model_name,
        )

    prompt = f"""
Evaluate the model answer against the reference answer.

<question>{question}</question>
<reference_answer>{reference}</reference_answer>
<model_answer>{prediction}</model_answer>

Return:
- score from 1 to 5
- correct = true only when the answer is materially correct
- short reasoning

Never copy information from the reference into the model answer. An empty or
unsupported model answer must be incorrect with score 1.
""".strip()
    try:
        llm = build_llm(settings=settings, temperature=0.0).with_structured_output(LLMJudgeDecision)
        decision = llm.invoke(prompt)
        return JudgeVerdict(
            score=decision.score,
            correct=decision.correct,
            reasoning=decision.reasoning,
            mode="llm_judge",
            provider=provider,
            model=settings.model_name,
        )
    except Exception as exc:
        score = 5 if _token_f1(reference, prediction) >= 0.95 else 3 if _token_f1(reference, prediction) >= 0.5 else 1
        return JudgeVerdict(
            score=score,
            correct=score >= 3,
            reasoning="Fallback heuristic judge used because the LLM evaluator was unavailable.",
            mode="token_f1_fallback",
            provider=provider,
            model=settings.model_name,
            fallback_used=True,
            error=f"{type(exc).__name__}: {exc}",
        )


def _run_ragas(settings: Settings, answers: list[dict[str, Any]]) -> dict[str, Any]:
    if os.getenv("RUN_RAGAS", "").lower() not in {"1", "true", "yes"}:
        return {"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."}
    try:
        if "langchain_community.chat_models.vertexai" not in sys.modules:
            shim = types.ModuleType("langchain_community.chat_models.vertexai")
            shim.ChatVertexAI = type("ChatVertexAI", (), {})
            sys.modules["langchain_community.chat_models.vertexai"] = shim
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

        dataset = Dataset.from_dict(
            {
                "question": [item["question"] for item in answers],
                "answer": [item["answer"] for item in answers],
                "ground_truth": [item["ground_truth"] for item in answers],
                "contexts": [item["retrieved_contexts"] for item in answers],
            }
        )
        result = evaluate(
            dataset,
            metrics=[answer_relevancy, context_precision, context_recall, faithfulness],
            llm=build_llm(settings=settings, temperature=0.0),
            embeddings=MiniLMEmbeddings(settings.embedding_model),
        )
        return dict(result)
    except Exception as exc:  # pragma: no cover
        return {"error": f"Ragas evaluation failed: {exc}"}


def evaluate_core_metrics(
    settings: Settings,
    index: LocalEmbeddingIndex,
    test_set_path,
) -> dict[str, float | int]:
    """Evaluate deterministic retrieval/F1 signals without invoking an LLM judge."""
    test_set = read_json(test_set_path)
    rows: list[dict[str, Any]] = []
    for item in test_set:
        result = answer_question(item["question"], settings=settings, index=index)
        rows.append(
            {
                "retrieval_hit": any(
                    doc_id in item["ground_truth_doc_ids"]
                    for doc_id in result.retrieved_doc_ids
                ),
                "token_f1": _token_f1(item["ground_truth"], result.answer),
            }
        )
    if not rows:
        return {"samples": 0, "retrieval_hit_rate": 0.0, "mean_token_f1": 0.0}
    return {
        "samples": len(rows),
        "retrieval_hit_rate": mean(1.0 if item["retrieval_hit"] else 0.0 for item in rows),
        "mean_token_f1": mean(item["token_f1"] for item in rows),
    }


def evaluate_pipeline(
    settings: Settings,
    index: LocalEmbeddingIndex,
    test_set_path,
    metrics_output_path,
    answers_output_path,
    answerer: Callable[[str], AnswerResult] | None = None,
) -> EvaluationBundle:
    test_set = read_json(test_set_path)
    answers: list[dict[str, Any]] = []

    for item in test_set:
        result = (
            answerer(item["question"])
            if answerer is not None
            else answer_question(item["question"], settings=settings, index=index)
        )
        judge = _judge_answer(
            settings,
            item["question_type"],
            item["question"],
            item["ground_truth"],
            result.answer,
        )
        retrieval_hit = any(doc_id in item["ground_truth_doc_ids"] for doc_id in result.retrieved_doc_ids)
        answers.append(
            {
                "id": item["id"],
                "question_type": item["question_type"],
                "question": item["question"],
                "ground_truth": item["ground_truth"],
                "ground_truth_doc_ids": item["ground_truth_doc_ids"],
                "answer": result.answer,
                "retrieved_doc_ids": result.retrieved_doc_ids,
                "retrieved_contexts": result.retrieved_contexts,
                "retrieval_hit": retrieval_hit,
                "exact_lookup_hit": result.exact_lookup_hit,
                "answer_source": result.answer_source,
                "answer_doc_id": result.answer_doc_id,
                "answerer_error": result.answerer_error,
                "token_f1": _token_f1(item["ground_truth"], result.answer),
                "judge": judge.model_dump(),
            }
        )

    judge_modes: dict[str, int] = {}
    for item in answers:
        mode = str(item["judge"]["mode"])
        judge_modes[mode] = judge_modes.get(mode, 0) + 1

    summary = {
        "samples": len(answers),
        "retrieval_hit_rate": mean(1.0 if item["retrieval_hit"] else 0.0 for item in answers),
        "exact_lookup_hit_rate": mean(1.0 if item["exact_lookup_hit"] else 0.0 for item in answers),
        "mean_token_f1": mean(item["token_f1"] for item in answers),
        "judge_accuracy": mean(1.0 if item["judge"]["correct"] else 0.0 for item in answers),
        "mean_judge_score": mean(item["judge"]["score"] for item in answers),
        "judge_provenance": {
            "provider": normalized_provider(settings),
            "model": settings.model_name,
            "modes": judge_modes,
            "fallback_samples": sum(1 for item in answers if item["judge"]["fallback_used"]),
        },
        "answerer_provenance": {
            "modes": {
                mode: sum(1 for item in answers if item["answer_source"] == mode)
                for mode in sorted({str(item["answer_source"]) for item in answers})
            },
            "fallback_samples": sum(1 for item in answers if item["answerer_error"]),
        },
    }
    summary["ragas"] = _run_ragas(settings, answers)

    bundle = EvaluationBundle(summary=summary, answers=answers)
    write_json(metrics_output_path, summary)
    write_json(answers_output_path, answers)
    return bundle
