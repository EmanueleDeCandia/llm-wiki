"""Parser PDF a stratifici (Skill §4-A.1).

Motore selezionabile via env `LLW_PDF_ENGINE`:
* `auto` (default): tenta `docling` (alta fedeltà: tabelle strutturate,
  gerarchia H1-H6, formule in LaTeX); se non è installato o non è
  raggiungibile (modelli su Hugging Face), degrada automaticamente al
  motore built-in.
* `pypdf`: motore built-in leggero — testo via layer testuale +
  **rilevatore di tabelle basato sul layout** (zero AI, zero dipendenze).
* `docling` / `marker`: vincolati (fallback built-in solo su errore).

Le formule matematiche passano sempre intatte: il built-in preserva il
layer testuale (con `$...$` quando presente), docling con
`LLW_PDF_FORMULAS=1` abilita l'enrichment formule in LaTeX vero.
"""
from __future__ import annotations

import io
import logging
import os
import re
import tempfile
from pathlib import Path

from ..schemas.wiki import ParsedDocument, ParsedTable
from .tables import Span, extract_tables_from_spans, parse_markdown_table, table_to_markdown

log = logging.getLogger("llmwiki.parsers.pdf")


class PdfParser:
    name = "pdf"

    def __init__(self, engine: str | None = None) -> None:
        self.engine = (engine or os.environ.get("LLW_PDF_ENGINE", "auto")).lower()
        self._docling_unavailable: bool | None = None  # cache negativa

    def parse(self, path: Path, vault_rel: str) -> ParsedDocument:
        data = path.read_bytes()
        if self.engine in ("docling", "marker"):
            try:
                return self._parse_high_fidelity(data, vault_rel, path)
            except Exception as exc:  # noqa: BLE001
                log.warning("engine %s non riuscito (%s): fallback pypdf", self.engine, exc)
        if self.engine == "auto" and not self._docling_unavailable:
            try:
                return self._parse_high_fidelity(data, vault_rel, path)
            except ImportError:
                self._docling_unavailable = True
                log.info("docling non installato: uso motore pypdf+tables")
            except Exception as exc:  # noqa: BLE001
                self._docling_unavailable = True
                log.warning("docling non raggiungibile (%s): uso motore pypdf+tables", exc)
        return self._parse_pypdf(data, vault_rel, path)

    # ------------------------------------------------------- built-in pypdf
    def _parse_pypdf(self, data: bytes, vault_rel: str, path: Path) -> ParsedDocument:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(data))
        page_blocks: list[str] = []
        tables: list[ParsedTable] = []
        for page in reader.pages:
            spans: list[Span] = []

            def _visit(text: str, cm, tm, font_dict, font_size) -> None:  # noqa: ANN001
                t = (text or "").strip()
                if t:
                    spans.append(Span(x=float(tm[4]), y=float(tm[5]), text=t))

            try:
                page.extract_text(visitor_text=_visit)
            except Exception:  # noqa: BLE001
                spans = []
            if spans:
                page_tables, table_rows = extract_tables_from_spans(spans)
                page_blocks.append(self._render_page(spans, table_rows))
                tables.extend(page_tables)
            else:
                # Fallback: estrazione senza layout
                page_blocks.append(page.extract_text() or "")

        raw = re.sub(r"\x00", "", "\n\n".join(b for b in page_blocks if b.strip()))
        raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
        return ParsedDocument(
            source_path=vault_rel,
            title=self._guess_title(raw, path),
            markdown=raw,
            headings=[self._guess_title(raw, path)],
            tables=tables,
            word_count=len(raw.split()),
            parser_name="pdf:pypdf+tables",
        )

    @staticmethod
    def _render_page(spans: list[Span], table_rows: set[int]) -> str:
        """Ricostruisce il flusso della pagina sostituendo le regioni
        tabellari con tabelle Markdown."""
        from .tables import Row, spans_to_rows

        rows = spans_to_rows(spans)
        out: list[str] = []
        i, n = 0, len(rows)
        while i < n:
            if i in table_rows:
                # trova la fine della regione
                j = i
                while j in table_rows and j < n:
                    j += 1
                grid: list[list[str]] = []
                for r in rows[i:j]:
                    grid.append([s.text for s in r.spans])
                out.append(_grid_to_markdown(grid))
                i = j
            else:
                out.append(" ".join(s.text for s in rows[i].spans))
                i += 1
        return "\n".join(out)

    @staticmethod
    def _guess_title(raw: str, path: Path) -> str:
        first_line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
        if 3 <= len(first_line) <= 120:
            return first_line
        return path.stem.replace("_", " ").replace("-", " ").title()

    # ----------------------------------------------- alta fedeltà (opzionale)
    def _parse_high_fidelity(self, data: bytes, vault_rel: str, path: Path) -> ParsedDocument:
        tmp = Path(tempfile.mkdtemp(prefix="llw-pdf-")) / path.name
        tmp.write_bytes(data)
        try:
            if self.engine == "marker":
                return self._parse_marker(tmp, vault_rel, path)
            return self._parse_docling(tmp, vault_rel, path)
        finally:
            try:
                tmp.unlink(missing_ok=True)
                tmp.parent.rmdir()
            except OSError:
                pass

    @staticmethod
    def _parse_docling(tmp: Path, vault_rel: str, path: Path) -> ParsedDocument:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling_core.types.doc import DocItemLabel

        opts = PdfPipelineOptions()
        opts.do_table_structure = True
        if os.environ.get("LLW_PDF_FORMULAS", "") == "1":
            try:
                opts.do_formula_enrichment = True  # LaTeX vero per le formule
            except Exception:  # noqa: BLE001
                pass
        conv = DocumentConverter(format_options={"pdf": PdfFormatOption(pipeline_options=opts)})
        result = conv.convert(str(tmp))
        markdown = result.document.export_to_markdown()
        tables: list[ParsedTable] = []
        for item, _level in result.document.iterate_items():
            if getattr(item, "label", None) == DocItemLabel.TABLE:
                try:
                    t = parse_markdown_table(item.export_to_markdown())
                    if t:
                        tables.append(t)
                except Exception:  # noqa: BLE001
                    continue
        return ParsedDocument(
            source_path=vault_rel,
            title=path.stem.replace("_", " ").replace("-", " ").title(),
            markdown=markdown.strip(),
            headings=[m.group(2).strip() for m in re.finditer(r"^(#{1,6})\s+(.+)$", markdown, re.MULTILINE)],
            tables=tables,
            word_count=len(markdown.split()),
            parser_name="pdf:docling",
        )

    @staticmethod
    def _parse_marker(tmp: Path, vault_rel: str, path: Path) -> ParsedDocument:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.output import text_from_rendered

        with PdfConverter(artifact_dict=create_model_dict()) as converter:
            rendered = converter(str(tmp))
        markdown, _, _ = text_from_rendered(rendered)
        return ParsedDocument(
            source_path=vault_rel,
            title=path.stem.replace("_", " ").replace("-", " ").title(),
            markdown=markdown.strip(),
            headings=[m.group(2).strip() for m in re.finditer(r"^(#{1,6})\s+(.+)$", markdown, re.MULTILINE)],
            tables=[],
            word_count=len(markdown.split()),
            parser_name="pdf:marker",
        )


def _grid_to_markdown(grid: list[list[str]]) -> str:
    """Griglia (righe di celle in ordine x) → tabella Markdown con header."""
    if not grid:
        return ""
    cols = max(len(r) for r in grid)
    rows = [r + [""] * (cols - len(r)) for r in grid]
    table = ParsedTable(header=rows[0], rows=rows[1:])
    return table_to_markdown(table)
