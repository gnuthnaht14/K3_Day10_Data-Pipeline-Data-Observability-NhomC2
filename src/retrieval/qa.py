from __future__ import annotations

from dataclasses import dataclass
import re

from core.config import Settings
from core.utils import first_sentence
from retrieval.index import LocalEmbeddingIndex, SearchResult


@dataclass(frozen=True)
class AnswerResult:
    question: str
    answer: str
    # These fields contain only semantic-search results.  Exact lookup may be
    # used to answer a title-addressed question, but it must not inflate the
    # retrieval metric.
    retrieved_doc_ids: list[str]
    retrieved_contexts: list[str]
    retrieved_titles: list[str]
    exact_lookup_hit: bool
    answer_source: str
    answer_doc_id: str | None
    answerer_error: str | None = None


def _extract_answer(question: str, top_result: SearchResult) -> str:
    lowered = question.lower()
    metadata = top_result.metadata
    if any(phrase in lowered for phrase in ("who authored", "list the authors", "who are the authors")):
        return str(metadata.get("authors_joined", "") or "").strip()
    if "when was" in lowered or "publication date" in lowered or "published on" in lowered:
        return str(metadata.get("published", "") or "").strip()
    if "what categories" in lowered or "what subject categories" in lowered:
        categories = str(metadata.get("categories_joined", "") or "").strip()
        return categories or "No subject categories are listed in the clean record."
    return first_sentence(str(metadata.get("summary", "") or ""))


def answer_question(question: str, settings: Settings, index: LocalEmbeddingIndex, top_k: int | None = None) -> AnswerResult:
    semantic_results = index.search(question, top_k=top_k)
    title_match = re.search(r"'([^']+)'", question)
    exact = index.lookup(title_match.group(1)) if title_match else None

    if exact:
        answer_result = SearchResult(
            paper_id=exact["paper_id"],
            title=exact["title"],
            score=1.0,
            content=exact["content"],
            metadata=exact["metadata"],
        )
        answer_source = "exact_lookup"
    elif semantic_results:
        answer_result = semantic_results[0]
        answer_source = "semantic_top1"
    else:
        answer_result = None
        answer_source = "no_result"

    if answer_result is None:
        answer = "I don't know from the indexed corpus."
    else:
        answer = _extract_answer(question, answer_result)

    return AnswerResult(
        question=question,
        answer=answer,
        retrieved_doc_ids=[item.paper_id for item in semantic_results],
        retrieved_contexts=[item.content for item in semantic_results],
        retrieved_titles=[item.title for item in semantic_results],
        exact_lookup_hit=exact is not None,
        answer_source=answer_source,
        answer_doc_id=answer_result.paper_id if answer_result is not None else None,
    )
