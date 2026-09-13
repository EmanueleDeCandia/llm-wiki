"""Configurazione applicativa (env + pydantic-settings)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LLM Wiki Desktop"
    api_host: str = "0.0.0.0"
    api_port: int = 8100

    # Sandbox computazionale (Skill §4 Pipeline C)
    sandbox_timeout_seconds: int = 30
    sandbox_python: str = ""  # vuoto => interpretere corrente

    # Layer LLM — NIENTE modelli AI abilitati per default.
    # "none" => motore deterministico offline (OpenAI/Anthropic/Ollama richiedano
    # chiave API esplicita; senza chiave la factory torna sempre il client offline).
    llm_provider: str = "none"  # none | openai | anthropic | ollama
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:7b"

    # Compilazione
    max_concept_notes_per_source: int = 12


settings = Settings()
