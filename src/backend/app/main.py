"""LLM Wiki — FastAPI sidecar (Skill §5.2).

Avvio: `uvicorn app.main:app --host 0.0.0.0 --port 8100` oppure `python run.py`.
L'applicazione è local-first: il solo stato è il vault su disco.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .core.config import settings
from .core.state import AppState

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("llmwiki")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Engine local-first di gestione della conoscenza compilata (LLM Wiki). "
        "Modalità di default: **offline deterministica** — nessun modello AI "
        "installato o invocato. Il layer LLM (OpenAI/Anthropic/Ollama) è un "
        "adattatore opzionale attivabile via configurazione."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # sidecar locale: UI Tauri/Electron o browser in sviluppo
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

state = AppState()

app.include_router(router)


@app.get("/")
def root() -> dict:
    return {
        "app": settings.app_name,
        "docs": "/docs",
        "health": "/api/v1/health",
        "mode": "offline-deterministic (LLM_PROVIDER=none)",
    }


log.info("LLM Wiki sidecar pronto — modalità %s", settings.llm_provider)
