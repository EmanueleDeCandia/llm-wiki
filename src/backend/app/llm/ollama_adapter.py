"""Adattatore Ollama / vLLM (runtime locali, Skill §5.2).

Attivo solo con `LLM_PROVIDER=ollama` e un server raggiungibile su
`OLLAMA_BASE_URL` (default http://127.0.0.1:11434). Permette inferenza
completamente offline con modelli locali (es. Qwen 2.5 Coder, Llama 3).
"""
from __future__ import annotations

import httpx

from .base import LLMResponse


class OllamaClient:
    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434",
                 model: str = "qwen2.5-coder:7b") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float = 0.2, max_tokens: int = 4096,
                 timeout: float = 300.0) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return LLMResponse(
            text=(data.get("message") or {}).get("content", ""),
            model=data.get("model", self.model),
            provider=self.name,
            usage={"total_duration": data.get("total_duration", 0)},
        )

    def ping(self) -> bool:
        try:
            httpx.get(f"{self.base_url}/api/tags", timeout=5)
            return True
        except httpx.HTTPError:
            return False
