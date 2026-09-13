"""LLM Abstraction Layer (Skill §5.2).

Interfaccia unificata per i provider: OpenAI, Anthropic Claude e runtime
locali (Ollama/vLLM). L'applicazione opera in modalità **offline
deterministica** quando `LLM_PROVIDER=none` (default): nessun modello AI è
installato, invocato o richiesto. I client qui sotto sono *client API*:
vengono istanziati e usati solo se il rispettivo provider è configurato e
raggiabile (chiave API o endpoint locale).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class LLMResponse:
    text: str
    model: str = ""
    provider: str = ""
    usage: dict = field(default_factory=dict)


@dataclass
class LLMError(Exception):
    message: str


@runtime_checkable
class LLMClient(Protocol):
    """Contratto minimale per qualsiasi provider (cloud o locale)."""

    name: str
    model: str

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> LLMResponse: ...

    def ping(self) -> bool:
        """Verifica di raggiungibilità senza consumare budget."""
        ...


def is_configured(client: LLMClient | None) -> bool:
    return client is not None
