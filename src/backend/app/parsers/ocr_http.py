"""Adattatore OCR HTTP (engine VLM locali) — `dotsmocr-http` / `deepseek2-http` / `ocr-http`.

Parla con un **servizio HTTP separato** che espone il contratto:

    POST {LLW_OCR_HTTP_URL}/parse      (multipart/form-data, campo "file" = PDF;
                                        campo opzionale "model" se LLW_OCR_HTTP_MODEL)
    → 200 {"markdown": "…"}            (accettato anche campo "text")

Il servizio esegue il VLM (dots.mocr, DeepSeek-OCR-2, …) su GPU: è un
processo indipendente dall'app. Così il backend resta leggero e l'OCR è
un servizio spendibile via env, senza dipendenze pesanti nel venv.
`tools/ocr_http_server.py` contiene un server di riferimento per
DeepSeek-OCR-2 (transformers) da eseguire sulla macchina con GPU.

Motori equivalente:
* `LLW_PDF_ENGINE=dotsmocr-http`  → dots.mocr (qualità + multilingua + SVG)
* `LLW_PDF_ENGINE=deepseek2-http` → DeepSeek-OCR-2 (velocità/leggerezza)
* `LLW_PDF_ENGINE=ocr-http`       → generico (modello via LLW_OCR_HTTP_MODEL)

In `auto`, se il layer testuale del PDF è rado (scansione/fax), l'engine
built-in cede il passo a questo engine; sui PDF born-digital densi il
built-in resta (veloce, gratuito, deterministico).

Configurazione: `LLW_OCR_HTTP_URL` (obbligatoria per questi engine),
`LLW_OCR_HTTP_API_KEY`, `LLW_OCR_HTTP_MODEL`, `LLW_OCR_HTTP_TIMEOUT_S`
(default 600), `LLW_PDF_SCAN_THRESHOLD` (caratteri/pagina sotto i quali
il PDF è considerato "scansione", default 20).

Privacy: con un servizio locale/LAN il PDF resta in rete propria.
Nessuna dipendenza aggiuntiva: si usa `urllib` dalla stdlib.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from ..schemas.wiki import ParsedDocument
from .tables import extract_markdown_tables

log = logging.getLogger("llmwiki.parsers.ocr_http")

# Alias di engine → nome canonico (parser_name e log)
OCR_ENGINE_ALIASES: dict[str, str] = {
    "ocr": "ocr-http",
    "ocr-http": "ocr-http",
    "ocrhttp": "ocr-http",
    "dotsmocr": "dotsmocr-http",
    "dotsmocr-http": "dotsmocr-http",
    "dots.mocr": "dotsmocr-http",
    "deepseek2": "deepseek2-http",
    "deepseek2-http": "deepseek2-http",
    "deepseek-ocr2": "deepseek2-http",
    "deepseek_ocr2": "deepseek2-http",
}


class OcrHttpError(RuntimeError):
    """Errore dell'engine OCR HTTP (config, rete, risposta inattesa)."""


class OcrHttpClient:
    def __init__(
        self,
        kind: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.kind = (kind or os.environ.get("LLW_OCR_HTTP_KIND", "")).lower() or None
        self.base_url = (base_url or os.environ.get("LLW_OCR_HTTP_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("LLW_OCR_HTTP_API_KEY", "")
        self.model = model or os.environ.get("LLW_OCR_HTTP_MODEL", "")
        self.timeout_s = timeout_s or float(os.environ.get("LLW_OCR_HTTP_TIMEOUT_S", "600"))

    def is_configured(self) -> bool:
        return bool(self.base_url)

    # ------------------------------------------------------------------ API
    def parse_pdf(self, data: bytes, file_name: str, vault_rel: str) -> ParsedDocument:
        if not self.is_configured():
            raise OcrHttpError("LLW_OCR_HTTP_URL non configurata")
        log.info("OCR HTTP (%s): invio %s al servizio %s", self.kind or "generico", file_name, self.base_url)
        markdown = self._parse(data, file_name)
        if not markdown.strip():
            raise OcrHttpError("il servizio OCR ha restituito un documento vuoto")
        headings = [m.group(2).strip() for m in re.finditer(r"^(#{1,6})\s+(.+)$", markdown, re.MULTILINE)]
        return ParsedDocument(
            source_path=vault_rel,
            title=self._title(markdown, file_name),
            markdown=markdown.strip(),
            headings=headings,
            tables=extract_markdown_tables(markdown),
            word_count=len(markdown.split()),
            parser_name=f"pdf:{self.kind or 'ocr'}-http",
        )

    # ------------------------------------------------------------------ HTTP
    def _parse(self, data: bytes, file_name: str) -> str:
        boundary = uuid4().hex
        safe_name = (file_name or "documento.pdf").replace('"', "'")[:200]
        parts = [
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
            "Content-Type: application/pdf\r\n\r\n".encode("utf-8"),
            data,
            b"\r\n",
        ]
        if self.model:
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n"
                f"{self.model}\r\n".encode("utf-8")
            )
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)

        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/parse", data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300]
            raise OcrHttpError(f"errore {exc.code} dal servizio OCR: {detail!r}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OcrHttpError(f"servizio OCR irraggiungibile ({self.base_url}): {exc}") from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise OcrHttpError("risposta OCR non valida (atteso JSON)") from exc

        if not isinstance(payload, dict):
            raise OcrHttpError(f"risposta OCR inattesa: {str(payload)[:200]}")
        md = payload.get("markdown") or payload.get("text") or payload.get("output")
        if isinstance(md, dict):  # {"result": {"markdown": …}}
            md = md.get("markdown") or md.get("text") or ""
        return md if isinstance(md, str) else ""

    @staticmethod
    def _title(markdown: str, file_name: str) -> str:
        m = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
        if m:
            return m.group(1).strip()
        return Path(file_name or "documento").stem.replace("_", " ").replace("-", " ").title()
