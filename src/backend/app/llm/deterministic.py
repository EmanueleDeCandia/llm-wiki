"""Client LLM offline: nessun modello, nessuna chiamata estera.

È l'implementazione by-default del layer LLM. Serve a:
* mantenere il contratto `LLMClient` attivo in tutto il codice (i moduli
  compilatore/agente non contengono ramificamenti "se l'AI c'è");
* restituire risposte esplicite che informano l'utente che la sintesi
  semantica è deterministica (nessun modello configurato).
"""
from __future__ import annotations

from .base import LLMResponse


class OfflineLLMClient:
    """Simbolo del provider assente: `complete` dichiara l'assenza invece di
    eseguire inferenza. La pipeline scende al fallback deterministico."""

    name = "offline"
    model = "none"

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float = 0.2, max_tokens: int = 4096,
                 timeout: float = 120.0) -> LLMResponse:
        return LLMResponse(
            text=(
                "Nessun modello AI configurato (LLM_PROVIDER=none). "
                "L'elaborazione è stata eseguita dal motore deterministico offline."
            ),
            model="none",
            provider="offline",
            usage={"offline": True},
        )

    def ping(self) -> bool:
        return False
