"""Adattatore OpenAI (REST, httpx — nessun SDK pesante).

Attivo solo con `LLM_PROVIDER=openai` + `OPENAI_API_KEY`. Compatibile con
qualsiasi endpoint OpenAI-compatible (es. `OPENAI_BASE_URL` verso vLLM).
"""
from __future__ import annotations

import httpx

from .base import LLMResponse


class OpenAIClient:
    name = "openai"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1",
                 model: str = "gpt-4o") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float = 0.2, max_tokens: int = 4096,
                 timeout: float = 120.0) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return LLMResponse(
            text=data["choices"][0]["message"]["content"] or "",
            model=data.get("model", self.model),
            provider=self.name,
            usage=data.get("usage", {}),
        )

    def ping(self) -> bool:
        try:
            httpx.get(f"{self.base_url}/models",
                      headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10)
            return True
        except httpx.HTTPError:
            return False
