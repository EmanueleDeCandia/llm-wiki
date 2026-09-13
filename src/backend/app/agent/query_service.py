"""Servizio di interrogazione delle note atomiche (endpoint /api/v1/agent/query).

Modalità offline (default): retrieval deterministico + composizione con
citazioni tracciabili. Con provider LLM configurato: lo stesso contesto
viene inviato al modello con il prompt SYSTEM_QUERY (compiler/prompts.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..compiler.links import LinkRegistry
from ..compiler.prompts import SYSTEM_QUERY, USER_QUERY_TEMPLATE
from ..core.vault import Vault
from ..index.index_builder import build_registry
from ..llm.base import LLMClient
from ..llm.deterministic import OfflineLLMClient
from .retriever import deterministic_answer, format_context, retrieve


@dataclass
class QueryResult:
    provider: str
    answer_markdown: str
    citations: list[dict] = field(default_factory=list)


def run_query(vault: Vault, question: str, llm: LLMClient | None = None,
              top_k: int = 5, registry: LinkRegistry | None = None) -> QueryResult:
    llm = llm or OfflineLLMClient()
    reg = registry or build_registry(vault)
    notes = retrieve(vault, reg, question, top_k=top_k)
    citations = [
        {"note": n.id, "title": n.title, "score": round(n.score, 3), "excerpt": n.excerpt}
        for n in notes
    ]

    if isinstance(llm, OfflineLLMClient):
        return QueryResult(
            provider="deterministic-offline",
            answer_markdown=deterministic_answer(question, notes),
            citations=citations,
        )

    context = format_context(notes)
    prompt = USER_QUERY_TEMPLATE.format(question=question, context=context)
    resp = llm.complete(prompt, system=SYSTEM_QUERY, temperature=0.1, max_tokens=2048)
    return QueryResult(
        provider=f"llm:{llm.name}:{llm.model}",
        answer_markdown=resp.text,
        citations=citations,
    )
