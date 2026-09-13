"""Avvio del sidecar: `python run.py` (host/port da env: API_HOST, API_PORT)."""
from __future__ import annotations

import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port,
                log_level="info")
