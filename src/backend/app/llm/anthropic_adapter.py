"""Adattatore Anthropic Claude (REST, httpx).

Attivo solo con `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`.
"""
from __future__ import annotations

import httpx

from .base import LLMResponse

API_VERSION = "2023-06-01"


class AnthropicClient:
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514",
                 base_url: str = "https://api.anthropic.com") -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float = 0.2, max_tokens: int = 4096,
                 timeout: float = 120.0) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        resp = httpx.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        return LLMResponse(
            text="".join(parts),
            model=data.get("model", self.model),
            provider=self.name,
            usage=data.get("usage", {}),
        )

    def ping(self) -> bool:
        try:
            httpx.get(f"{self.base_url}/v1/models",
                      headers={"x-api-key": self.api_key,
                               "anthropic-version": API_VERSION}, timeout=10)
            return True
        except httpx.HTTPError:
            return False
