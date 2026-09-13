"""Adapter LlamaParse (API cloud LlamaIndex) — engine `llamaparse`.

Invia il PDF all'endpoint di conversione (`POST /convert`, polling su
`GET /{id}`) e restituisce il `ParsedDocument` con il Markdown prodotto:
tabelle già formattate in Markdown e formule in LaTeX (a seconda del
piano/modo di parsing configurato sul provider).

ATTENZIONE privacy: con questo engine il PDF lascia la macchina.
Riservarlo a documenti non sensibili; per dati riservati preferire
engine locali (`pypdf`, `docling`) o un deploy privato.

Configurazione: `LLAMAPARSE_API_KEY` (obbligatoria per questo engine).
Nessuna dipendenza aggiuntiva: si usa `urllib` dalla stdlib.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from ..schemas.wiki import ParsedDocument
from .tables import extract_markdown_tables

log = logging.getLogger("llmwiki.parsers.llamaparse")

DEFAULT_BASE_URL = "https://cloud.llamaindex.ai/api/parsing"


class LlamaParseError(RuntimeError):
    """Errore dell'engine cloud (config, rete, risposta inattesa)."""


class LlamaParseClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 300.0,
        poll_interval_s: float = 1.5,
    ) -> None:
        self.api_key = api_key or os.environ.get("LLAMAPARSE_API_KEY", "")
        self.base_url = (
            base_url or os.environ.get("LLW_LLAMAPARSE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout_s = timeout_s
        self.poll_interval_s = poll_interval_s

    def is_configured(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------ API
    def parse_pdf(self, data: bytes, file_name: str, vault_rel: str) -> ParsedDocument:
        if not self.is_configured():
            raise LlamaParseError("LLAMAPARSE_API_KEY non configurata")
        result_id = self._convert(data, file_name)
        log.info("LlamaParse: conversione %s avviata (id=%s)", file_name, result_id)
        payload = self._wait(result_id)
        markdown = self._extract_markdown(payload)
        if not markdown.strip():
            raise LlamaParseError("LlamaParse ha restituito un documento vuoto")
        headings = [m.group(2).strip() for m in re.finditer(r"^(#{1,6})\s+(.+)$", markdown, re.MULTILINE)]
        return ParsedDocument(
            source_path=vault_rel,
            title=self._title(markdown, file_name),
            markdown=markdown.strip(),
            headings=headings,
            tables=extract_markdown_tables(markdown),
            word_count=len(markdown.split()),
            parser_name="pdf:llamaparse",
        )

    def _convert(self, data: bytes, file_name: str) -> str:
        body = {
            "source": base64.b64encode(data).decode("ascii"),
            "source_type": "data",
            "file_name": file_name,
            "options": {
                "chunking": "none",
                "include_page_images": False,
            },
        }
        out = self._post_json("/convert", body)
        result_id = out.get("id") or out.get("result_id")
        if not result_id:
            raise LlamaParseError(f"risposta inattesa da LlamaParse: {str(out)[:300]}")
        return str(result_id)

    def _wait(self, result_id: str) -> dict:
        deadline = time.monotonic() + self.timeout_s
        while True:
            payload = self._get_json(f"{self.base_url}/{result_id}")
            status = str(payload.get("status", "")).upper()
            if status in ("SUCCEEDED", "SUCCESS", "COMPLETED"):
                return payload
            if status in ("FAILED", "ERROR", "EXPIRED", "CANCELLED"):
                err = payload.get("error") or payload.get("failure_reason") or status
                raise LlamaParseError(f"conversione LlamaParse fallita: {err}")
            if time.monotonic() > deadline:
                raise LlamaParseError(f"timeout dopo {self.timeout_s:.0f}s in attesa di LlamaParse")
            time.sleep(self.poll_interval_s)

    def _extract_markdown(self, payload: dict) -> str:
        pd = payload.get("parsed_document")
        if isinstance(pd, dict):
            for key in ("markdown", "text"):
                v = pd.get(key)
                if isinstance(v, str) and v.strip():
                    return v
        for key in ("markdown", "text"):
            v = payload.get(key)
            if isinstance(v, str) and v.strip():
                return v
        # alcune versioni restituiscono un URL al risultato JSON
        url = payload.get("result")
        if isinstance(url, str) and url.startswith("http"):
            sub = self._get_json(url)
            if isinstance(sub, dict):
                for key in ("markdown", "text"):
                    v = sub.get(key)
                    if isinstance(v, str) and v.strip():
                        return v
        return ""

    @staticmethod
    def _title(markdown: str, file_name: str) -> str:
        m = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
        if m:
            t = m.group(1).strip()
            if 3 <= len(t) <= 120:
                return t
        return Path(file_name).stem.replace("_", " ").replace("-", " ").title()

    # ----------------------------------------------------------------- HTTP
    def _post_json(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return self._open(req)

    def _get_json(self, url: str) -> dict:
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        return self._open(req)

    def _open(self, req: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise LlamaParseError(f"HTTP {exc.code} da LlamaParse: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LlamaParseError(f"errore di rete verso LlamaParse: {exc}") from exc
