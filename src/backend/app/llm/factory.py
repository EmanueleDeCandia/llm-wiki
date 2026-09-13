"""Factory del provider LLM basato sulla configurazione (env / .env).

Policy di default della piattaforma: **nessun modello AI attivo**.
`LLM_PROVIDER=none` (default) restituisce `OfflineLLMClient` e l'engine
procede in modalità deterministica. Le chiavi API, se presenti, NON
abilitano automaticamente un provider: serve la scelta esplicita via env.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core.config import settings
from .anthropic_adapter import AnthropicClient
from .base import LLMClient, LLMResponse
from .deterministic import OfflineLLMClient
from .openai_adapter import OpenAIClient
from .ollama_adapter import OllamaClient


@dataclass
class LLMStatus:
    provider: str
    model: str
    configured: bool
    reachable: bool
    description: str


def get_llm_client() -> LLMClient:
    provider = (settings.llm_provider or "none").strip().lower()
    if provider in ("", "none", "offline", "deterministic"):
        return OfflineLLMClient()
    if provider == "openai":
        if not settings.openai_api_key:
            return OfflineLLMClient()
        return OpenAIClient(settings.openai_api_key, settings.openai_base_url,
                            settings.openai_model)
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            return OfflineLLMClient()
        return AnthropicClient(settings.anthropic_api_key, settings.anthropic_model)
    if provider in ("ollama", "vllm"):
        return OllamaClient(settings.ollama_base_url, settings.ollama_model)
    return OfflineLLMClient()


def llm_status() -> LLMStatus:
    client = get_llm_client()
    if isinstance(client, OfflineLLMClient):
        return LLMStatus(
            provider="none", model="none", configured=False, reachable=False,
            description=(
                "Modalità offline deterministica: nessun modello AI installato o "
                "configurato. Per abilitare la sintesi semantica: LLM_PROVIDER="
                "openai|anthropic|ollama + credenziali in src/backend/.env"
            ),
        )
    reachable = False
    try:
        reachable = client.ping()
    except Exception:  # noqa: BLE001
        reachable = False
    return LLMStatus(
        provider=client.name,
        model=client.model,
        configured=True,
        reachable=reachable,
        description=f"Provider {client.name} (modello {client.model}) "
                    + ("raggiungibile" if reachable else "non raggiungibile"),
    )
