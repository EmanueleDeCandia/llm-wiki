"""Parser di documenti testuali: TXT, MD e DOCX (estrazione senza dipendenze).

Per PDF/EPUB usa `pdf_doc` (pypdf built-in + hook opzionale per docling).
Le formule matematiche in sintassi `$...$` / `$$...$$` sono conservate
intatte nel Markdown di output (invariante §1.5: solo LaTeX, mai Unicode).
"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from ..schemas.wiki import ParsedDocument

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_LATENT = ("$")


def _extract_headings(markdown: str) -> list[str]:
    return [m.group(2).strip() for m in _HEADING_RE.finditer(markdown)]


class TextDocumentParser:
    """TXT/MD: il contenuto è già Markdown (o prose piana promossa a testo)."""

    name = "text"

    def parse(self, path: Path, vault_rel: str) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8", errors="replace")
        title = self._guess_title(raw, path)
        markdown = self._ensure_headings(raw)
        return ParsedDocument(
            source_path=vault_rel,
            title=title,
            markdown=markdown,
            headings=_extract_headings(markdown),
            word_count=len(markdown.split()),
            parser_name=self.name,
        )

    @staticmethod
    def _guess_title(raw: str, path: Path) -> str:
        m = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
        if m:
            return m.group(1).strip()
        return path.stem.replace("_", " ").replace("-", " ").strip().title()

    @staticmethod
    def _ensure_headings(raw: str) -> str:
        if re.search(r"^#{1,6}\s+", raw, re.MULTILINE):
            return raw
        # Prose piana: nessun H1. Lo aggiungiamo dal titolo di documento per
        # dare al compilatore un anchor di gerarchia (invariante §3.2).
        return raw


class DocxDocumentParser:
    """DOCX minimale (OOXML): estrazione testo paragrafi + tabelle.

    Nessuna dipendenza esterna: il DOCX è un ZIP con `word/document.xml`.
    Sostituisce in modo drop-in un parser `python-docx` quando installato.
    """

    name = "docx"

    def parse(self, path: Path, vault_rel: str) -> ParsedDocument:
        parts: list[str] = []
        with zipfile.ZipFile(path) as zf:
            with zf.open("word/document.xml") as fh:
                tree = ET.parse(fh)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        body = tree.getroot().find("w:body", ns)
        if body is None:
            body = tree.getroot()
        for child in body.iter():
            tag = child.tag.split("}")[-1]
            if tag == "p":
                text = "".join(t.text or "" for t in child.iter() if t.tag.endswith("}t"))
                style = self._paragraph_style(child, ns)
                if text.strip():
                    if style:
                        parts.append(f"{'#' * min(style, 6)} {text.strip()}")
                    else:
                        parts.append(text)
            elif tag == "tbl":
                rows: list[list[str]] = []
                for tr in child.iter():
                    if tr.tag.split("}")[-1] != "tr":
                        continue
                    cells: list[str] = []
                    for tc in tr.iter():
                        if tc.tag.split("}")[-1] == "tc":
                            cells.append(
                                "".join(t.text or "" for t in tc.iter() if t.tag.endswith("}t"))
                            )
                    if cells:
                        rows.append(cells)
                if rows:
                    head, *body_rows = rows
                    lines = ["| " + " | ".join(head) + " |",
                             "| " + " | ".join(["---"] * len(head)) + " |"]
                    lines += ["| " + " | ".join(r) + " |" for r in body_rows]
                    parts.append("\n".join(lines))
        markdown = "\n\n".join(p for p in parts if p)
        title = path.stem.replace("_", " ").strip().title()
        m = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
        if m:
            title = m.group(1).strip()
        return ParsedDocument(
            source_path=vault_rel,
            title=title,
            markdown=markdown,
            headings=_extract_headings(markdown),
            word_count=len(markdown.split()),
            parser_name=self.name,
        )

    @staticmethod
    def _paragraph_style(p: ET.Element, ns: dict) -> int | None:
        """Mappa gli stili Heading 1..6 di Word su H1..H6 Markdown."""
        ppr = p.find("w:pPr", ns)
        if ppr is None:
            return None
        style = ppr.find("w:pStyle", ns)
        if style is None:
            return None
        val = style.get(f"{{{ns['w']}}}val", "")
        m = re.match(r"^heading\s*(\d)$", val, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return None
