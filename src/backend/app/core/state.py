"""Stato di processo dell'application sidecar (vault attivo singleton)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..core.vault import Vault


@dataclass
class AppState:
    vault: Vault | None = None
    opened_at: datetime | None = None
    last_operation_error: str | None = field(default=None, repr=False)

    def require_vault(self) -> Vault:
        if self.vault is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=409, detail="Nessun vault aperto: invia POST /api/v1/vault/open")
        return self.vault
