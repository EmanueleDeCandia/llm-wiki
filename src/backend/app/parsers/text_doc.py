"""Parser di documenti testuali: TXT, MD e DOCX (estrazione senza dipendenze).

Per PDF/EPUB usa `pdf_doc` (pypdf built-in + hook opzionale per docling).
Le formule matematiche in sintassi `$...$` / `$$...$$` sono conservate
intatte nel Markdown di output (invariante §1.5: solo LaTeX, mai Unicode).

Documenti Markdown (output di engine OCR esterni: dots.mocr,
DeepSeek-OCR-2, LlamaParse, …):
* un eventuale frontmatter YAML iniziale viene *rimosso* dal corpo e
  preservato come `metadata` strutturata (provenienza: source, engine, …);
  la chiave `title`, se presente, diventa il titolo del documento;
* le tabelle Markdown (`| ... |`) sono estratte come `ParsedTable` con lo
  stesso contratto dei PDF, così compilatore e Sandbox le trattano allo
  stesso modo;
* i riferimenti a immagini relative (`![](imgs/x.png)`) possono essere
  riscritti verso percorsi dentro il vault tramite `image_map` (import
  cartelle OCR).
"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from ..schemas.wiki import ParsedDocument
from .tables import extract_markdown_tables

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_IMG_REF_RE = re.compile(r"(!\[[^\]]*\])\(([^)]+)\)")
_LATENT = ("$",)


def _extract_headings(markdown: str) -> list[str]:
    return [m.group(2).strip() for m in _HEADING_RE.finditer(markdown)]


class TextDocumentParser:
    """TXT/MD: il contenuto è già Markdown (o prose piana promossa a testo)."""

    name = "text"

    def parse(self, path: Path, vault_rel: str, image_map: dict[str, str] | None = None) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8", errors="replace")
        metadata: dict[str, str] = {}
        title_override: str | None = None
        body = raw
        fm = self._split_frontmatter(raw)
        if fm is not None:
            data, body = fm
            for k, v in data.items():
                if v is None or isinstance(v, (dict, list)):
                    continue
                metadata[str(k)] = str(v)
            if metadata.get("title"):
                title_override = metadata["title"]
        title = title_override or self._guess_title(body, path)
        markdown = self._rewrite_image_refs(self._ensure_headings(body), image_map)
        return ParsedDocument(
            source_path=vault_rel,
            title=title,
            markdown=markdown,
            headings=_extract_headings(markdown),
            tables=extract_markdown_tables(markdown),
            word_count=len(markdown.split()),
            parser_name=self.name,
            metadata=metadata,
        )

    @staticmethod
    def _split_frontmatter(raw: str) -> tuple[dict, str] | None:
        """Frontmatter YAML iniziale (`--- … ---`): restituisce (dati, corpo).

        Assente (o non-JSON mapping) → None: il corpo resta intatto.
        """
        if not raw.startswith("---"):
            return None
        end = raw.find("\n---", 3)
        if end == -1:
            return None
        header = raw[3:end].strip()
        body = raw[end + 4 :].lstrip("\n")
        try:
            data = yaml.safe_load(header)
        except yaml.YAMLError:
            return None
        if not isinstance(data, dict) or not data:
            return None
        return data, body

    @staticmethod
    def _rewrite_image_refs(markdown: str, image_map: dict[str, str] | None) -> str:
        """Riscrive `![alt](ref)` → `![alt](vault_rel)` per i ref in image_map.

        I riferimenti assoluti (http/https/data:) restano immutati.
        """
        if not image_map:
            return markdown

        def _sub(m: re.Match) -> str:
            bang_alt, target = m.group(1), m.group(2).strip()
            ref = target.split()[0].strip("<>")  # scarta titolo opzionale "…"
            if ref.startswith(("http://", "https://", "data:")):
                return m.group(0)
            repl = image_map.get(ref)
            return f"{bang_alt}({repl})" if repl else m.group(0)

        return _IMG_REF_RE.sub(_sub, markdown)

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
                    for tc in child.iter():
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
            tables=extract_markdown_tables(markdown),
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
