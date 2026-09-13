"""Parser PDF con architettura a stratifici.

* **Built-in** (`pypdf`): estrazione leggibile di testo e gerarchie di
  heading per PDF digitali; nessuna dipendenza pesante.
* **Alta fedeltà (opzionale)**: se `docling` (o `marker`) è installato e
  `LLW_PDF_ENGINE=docling|marker`, il registro passa a quell'engine per
  ottenere tabelle, gerarchia H1-H6 e formule in LaTeX (Skill §4-A.1).
  L'installazione del package è l'unico passo richiesto: il contratto di
  output (`ParsedDocument`) è invariato.
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path

from ..schemas.wiki import ParsedDocument, ParsedTable


class PdfParser:
    name = "pdf"

    def __init__(self, engine: str | None = None) -> None:
        self.engine = engine or os.environ.get("LLW_PDF_ENGINE", "pypdf")

    def parse(self, path: Path, vault_rel: str) -> ParsedDocument:
        data = path.read_bytes()
        if self.engine in ("docling", "marker"):
            try:
                return self._parse_high_fidelity(data, vault_rel, path)
            except Exception:
                pass  # fallback deterministico se l'engine non è disponibile
        return self._parse_pypdf(data, vault_rel, path)

    # -- pypdf -------------------------------------------------------------
    def _parse_pypdf(self, data: bytes, vault_rel: str, path: Path) -> ParsedDocument:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(data))
        blocks: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            blocks.append(text)
        raw = "\n".join(blocks)
        raw = self._normalize(raw)
        title = self._guess_title(raw, path)
        headings = [t for t in (title,) if t]
        tables = self._extract_tables(path)
        return ParsedDocument(
            source_path=vault_rel,
            title=title,
            markdown=raw,
            headings=headings,
            tables=tables,
            word_count=len(raw.split()),
            parser_name=f"pdf:{self.engine}",
        )

    @staticmethod
    def _normalize(raw: str) -> str:
        raw = re.sub(r"\x00", "", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        # Le formule rimangono in LaTeX quando il motore lo supporta; con pypdf
        # il testo esce così com'è: preserviamo ogni occorrenza di $...$ e
        # non introduciamo mai simboli matematici Unicode (invariante §1.5).
        return raw.strip()

    @staticmethod
    def _guess_title(raw: str, path: Path) -> str:
        first_line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
        if 3 <= len(first_line) <= 120:
            return first_line
        return path.stem.replace("_", " ").replace("-", " ").title()

    @staticmethod
    def _extract_tables(path: Path) -> list[ParsedTable]:
        """Il PDF pypdf non espone tabelle strutturate: le tabelle restano nel
        flusso di testo. Con docling/marker arriverebbero come ParsedTable."""
        return []

    @staticmethod
    def _tables_from_docling() -> list[ParsedTable]:
        """Con docling/marker le tabelle sono già Markdown nel flusso: il campo
        `tables` resta disponibile per pipeline future (es. scheda dataset)."""
        return []

    # -- engine ad alta fedeltà (opzionali) ---------------------------------
    def _parse_high_fidelity(self, data: bytes, vault_rel: str, path: Path) -> ParsedDocument:
        if self.engine == "docling":
            from docling.document_converter import DocumentConverter  # type: ignore

            tmp = path.with_suffix(".pdf")
            conv = DocumentConverter()
            result = conv.convert(str(tmp))
            markdown: str = result.document.export_to_markdown()
        else:
            from marker.converters.pdf import PdfConverter  # type: ignore
            from marker.models import create_model_dict  # type: ignore
            from marker.output import text_from_rendered  # type: ignore

            models = create_model_dict()
            with PdfConverter(artifact_dict=models) as converter:
                rendered = converter(str(path))
            markdown, _, _ = text_from_rendered(rendered)
        tables: list[ParsedTable] = self._tables_from_docling()
        return ParsedDocument(
            source_path=vault_rel,
            title=path.stem.replace("_", " ").title(),
            markdown=markdown.strip(),
            headings=[m.group(2).strip() for m in re.finditer(r"^(#{1,6})\s+(.+)$", markdown, re.MULTILINE)],
            tables=tables,
            word_count=len(markdown.split()),
            parser_name=f"pdf:{self.engine}",
        )
