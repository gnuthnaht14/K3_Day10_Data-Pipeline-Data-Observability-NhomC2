from __future__ import annotations

from dataclasses import replace
from typing import Any

from langchain.agents import create_agent
from langchain.tools import tool

from core.config import Settings
from retrieval.index import LocalEmbeddingIndex
from retrieval.llm import build_llm
from retrieval.qa import AnswerResult, answer_question


def build_agent(settings: Settings, index: LocalEmbeddingIndex):
    @tool
    def semantic_search_papers(query: str, top_k: int = 4) -> str:
        """Search the local paper corpus with embeddings and return the most relevant papers."""
        results = index.search(query, top_k=top_k)
        lines = []
        for result in results:
            lines.append(
                f"paper_id: {result.paper_id}\n"
                f"title: {result.title}\n"
                f"score: {result.score:.4f}\n"
                f"{result.content}"
            )
        return "\n\n".join(lines)

    @tool
    def lookup_paper(paper_id_or_title: str) -> str:
        """Look up a paper by exact paper_id or exact title from the local corpus."""
        record = index.lookup(paper_id_or_title)
        if not record:
            return "No exact paper match found."
        return (
            f"paper_id: {record['paper_id']}\n"
            f"title: {record['title']}\n"
            f"{record['content']}"
        )

    llm = build_llm(settings=settings, temperature=0.0)
    return create_agent(
        model=llm,
        tools=[semantic_search_papers, lookup_paper],
        system_prompt=(
            "You answer questions about the indexed scholarly paper corpus sourced from Crossref. "
            "Use tools before answering factual questions. "
            "If the indexed corpus does not support the answer, say so clearly."
        ),
        name="paper_corpus_agent",
    )


def run_agent_question(agent: Any, question: str) -> str:
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    messages = result.get("messages", [])
    if not messages:
        return ""
    final_message = messages[-1]
    return getattr(final_message, "content", str(final_message))


class TraceableAgentAnswerer:
    """Use the tool-calling agent while preserving an independent retrieval trace."""

    def __init__(self, settings: Settings, index: LocalEmbeddingIndex):
        self.settings = settings
        self.index = index
        self.agent = build_agent(settings, index)

    def __call__(self, question: str) -> AnswerResult:
        # Only this independent semantic trace feeds retrieval_hit_rate.
        trace = answer_question(question, settings=self.settings, index=self.index)
        try:
            answer = run_agent_question(self.agent, question).strip()
            return replace(
                trace,
                answer=answer,
                answer_source="langchain_tool_agent",
                answer_doc_id=None,
            )
        except Exception as exc:
            return replace(
                trace,
                answer_source=f"{trace.answer_source}_agent_fallback",
                answerer_error=f"{type(exc).__name__}: {exc}",
            )


def build_agent_answerer(settings: Settings, index: LocalEmbeddingIndex) -> TraceableAgentAnswerer:
    return TraceableAgentAnswerer(settings, index)
