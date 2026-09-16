"""Parser PDF a strati (Skill §4-A.1).

Motore selezionabile via env `LLW_PDF_ENGINE`:
* `auto` (default): prova `docling` (alta fedeltà: tabelle strutturate,
  gerarchia H1-H6, formule LaTeX); se non è installato o non è raggiungibile
  (modelli su Hugging Face), valuta l'engine **OCR HTTP** locale (se
  `LLW_OCR_HTTP_URL` è configurata): il PDF passa al VLM solo quando il
  layer testuale è rado (scansione/fax), altrimenti resta il built-in;
  poi prova `llamaparse` cloud (se `LLAMAPARSE_API_KEY` è configurata),
  infine degrada al motore built-in.
* `pypdf`: motore built-in leggero — testo via layer testuale +
  **rilevatore di tabelle**: PyMuPDF `find_tables` (PDF con linee di
  separazione, incluso booktabs) + euristica su coordinate per tabelle
  allineate senza linee (zero AI).
* `docling` / `marker`: vincolati (fallback built-in solo su errore).
* `llamaparse`: API cloud LlamaIndex — Markdown con tabelle e formule;
  richiede `LLAMAPARSE_API_KEY`; il PDF lascia la macchina.
* `dotsmocr-http` / `deepseek2-http` / `ocr-http`: VLM OCR locali eseguiti
  da un servizio HTTP separato (dots.mocr, DeepSeek-OCR-2, …) —
  richiede `LLW_OCR_HTTP_URL`; il PDF resta in rete propria.

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
from .llama_parse import LlamaParseClient, LlamaParseError
from .ocr_http import OCR_ENGINE_ALIASES, OcrHttpClient, OcrHttpError
from .tables import Span, extract_tables_from_spans, parse_markdown_table, table_to_markdown

log = logging.getLogger("llmwiki.parsers.pdf")

_LLAMA_ALIASES = {"llamaparse", "llama", "llama-parse"}
_OCR_ENGINES = {v for v in OCR_ENGINE_ALIASES.values()}


def _scan_threshold() -> float:
    """Sotto questa densità (caratteri/pagina) il PDF è considerato scansione."""
    try:
        return float(os.environ.get("LLW_PDF_SCAN_THRESHOLD", "20"))
    except ValueError:
        return 20.0


class PdfParser:
    name = "pdf"

    def __init__(self, engine: str | None = None) -> None:
        raw = (engine or os.environ.get("LLW_PDF_ENGINE", "auto")).lower()
        self.engine = OCR_ENGINE_ALIASES.get(raw, raw)
        self._docling_unavailable: bool | None = None  # cache negativa

    def _ocr_client(self, kind: str | None = None) -> OcrHttpClient:
        # "dotsmocr-http" → kind "dotsmocr" (il suffisso -http è del parser_name)
        if kind and kind.endswith("-http"):
            kind = kind[: -len("-http")]
        return OcrHttpClient(kind=kind)

    def parse(self, path: Path, vault_rel: str) -> ParsedDocument:
        data = path.read_bytes()
        if self.engine in ("docling", "marker"):
            try:
                return self._parse_high_fidelity(data, vault_rel, path)
            except Exception as exc:  # noqa: BLE001
                log.warning("engine %s non riuscito (%s): fallback pypdf", self.engine, exc)
        if self.engine in _LLAMA_ALIASES:
            client = LlamaParseClient()
            if not client.is_configured():
                raise LlamaParseError(
                    "engine 'llamaparse' selezionato ma LLAMAPARSE_API_KEY non configurata"
                )
            return client.parse_pdf(data, path.name, vault_rel)
        if self.engine in _OCR_ENGINES:
            client = self._ocr_client(self.engine)
            if not client.is_configured():
                raise OcrHttpError(
                    f"engine '{self.engine}' selezionato ma LLW_OCR_HTTP_URL non configurata"
                )
            return client.parse_pdf(data, path.name, vault_rel)
        if self.engine == "auto":
            if not self._docling_unavailable:
                try:
                    return self._parse_high_fidelity(data, vault_rel, path)
                except ImportError:
                    self._docling_unavailable = True
                    log.info("docling non installato: valuto engine OCR/cloud/built-in")
                except Exception as exc:  # noqa: BLE001
                    self._docling_unavailable = True
                    log.warning("docling non raggiungibile (%s): valuto engine OCR/cloud/built-in", exc)
            # OCR VLM locale (dots.mocr / DeepSeek-OCR-2 / generico HTTP):
            # usato solo quando il layer testuale è rado (scansione/fax).
            ocr = self._ocr_client(None)
            if ocr.is_configured():
                cheap = self._parse_pypdf(data, vault_rel, path)
                density = self._text_density(data, cheap)
                if density >= _scan_threshold():
                    log.info(
                        "layer testuale denso (%.0f car./pag): kept built-in", density
                    )
                    return cheap
                log.info(
                    "layer testuale rado (%.0f car./pag < %.0f): escalo all'engine OCR HTTP",
                    density,
                    _scan_threshold(),
                )
                try:
                    return ocr.parse_pdf(data, path.name, vault_rel)
                except OcrHttpError as exc:
                    log.warning("OCR HTTP non riuscito (%s): fallback built-in", exc)
                    return cheap
            client = LlamaParseClient()
            if client.is_configured():
                try:
                    log.info("nessun engine locale disponibile: uso LlamaParse (cloud)")
                    return client.parse_pdf(data, path.name, vault_rel)
                except LlamaParseError as exc:
                    log.warning("LlamaParse non riuscito (%s): uso motore built-in", exc)
        return self._parse_pypdf(data, vault_rel, path)

    @staticmethod
    def _text_density(data: bytes, doc: ParsedDocument) -> float:
        """Caratteri di testo estratti per pagina (stima per instradamento)."""
        try:
            import pypdf

            pages = len(pypdf.PdfReader(io.BytesIO(data)).pages) or 1
        except Exception:  # noqa: BLE001
            pages = 1
        return len(doc.markdown) / pages

    # ------------------------------------------------------- built-in (pypdf + pymupdf)
    def _parse_pypdf(self, data: bytes, vault_rel: str, path: Path) -> ParsedDocument:
        import pypdf

        fitz_doc = self._open_fitz(data)
        reader = pypdf.PdfReader(io.BytesIO(data))
        page_blocks: list[str] = []
        tables: list[ParsedTable] = []
        used_pymupdf = False
        for idx, page in enumerate(reader.pages):
            spans: list[Span] = []

            def _visit(text: str, cm, tm, font_dict, font_size) -> None:  # noqa: ANN001
                t = (text or "").strip()
                if t:
                    spans.append(Span(x=float(tm[4]), y=float(tm[5]), text=t))

            try:
                page.extract_text(visitor_text=_visit)
            except Exception:  # noqa: BLE001
                spans = []
            if not spans:
                # Fallback: estrazione senza layout
                page_blocks.append(page.extract_text() or "")
                continue

            # 1) tabelle con linee di separazione (PyMuPDF, se disponibile)
            page_h = 792.0
            fitz_tables: list[tuple] = []
            if fitz_doc is not None and idx < len(fitz_doc):
                page_h, fitz_tables = self._fitz_tables(fitz_doc, idx)
                if fitz_tables:
                    used_pymupdf = True

            # 2) gli span dentro le regioni tabellari non vanno nel testo libero
            free_spans = self._exclude_table_spans(spans, fitz_tables, page_h)
            # 3) euristica su coordinate per tabelle senza linee
            page_tables, table_rows = extract_tables_from_spans(free_spans)
            tables.extend(page_tables)
            for _bbox, md in fitz_tables:
                t = parse_markdown_table(md)
                if t is not None:
                    tables.append(t)
            page_blocks.append(self._render_page(page_h, free_spans, table_rows, fitz_tables))

        raw = re.sub(r"\x00", "", "\n\n".join(b for b in page_blocks if b.strip()))
        raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
        return ParsedDocument(
            source_path=vault_rel,
            title=self._guess_title(raw, path),
            markdown=raw,
            headings=[self._guess_title(raw, path)],
            tables=tables,
            word_count=len(raw.split()),
            parser_name="pdf:pymupdf+tables" if used_pymupdf else "pdf:pypdf+tables",
        )

    @staticmethod
    def _open_fitz(data: bytes):
        """Apri il documento con PyMuPDF (opzionale) per la table detection."""
        try:
            import pymupdf as fitz
        except ImportError:
            return None
        try:
            doc = fitz.open(stream=data, filetype="pdf")
            if len(doc) == 0:
                return None
            return doc
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _fitz_tables(fitz_doc, idx: int) -> tuple[float, list[tuple]]:
        """Tabelle della pagina (strategy 'lines') → (altezza pagina, [(bbox, markdown)])."""
        page = fitz_doc[idx]
        page_h = float(page.rect.height)
        try:
            found = page.find_tables(strategy="lines")
        except Exception as exc:  # noqa: BLE001
            log.debug("pymupdf find_tables fallita (pagina %s): %s", idx, exc)
            return page_h, []
        out: list[tuple] = []
        for t in found.tables:
            try:
                md = (t.to_markdown() or "").strip()
                b = t.bbox
                # bbox è fitz.Rect nelle versioni < 1.28, tuple nelle successive
                box = (float(b.x0), float(b.y0), float(b.x1), float(b.y1)) if hasattr(b, "x0") else tuple(float(v) for v in b)
                if md and box[2] > box[0] and box[3] > box[1]:
                    out.append((box, md))
            except Exception:  # noqa: BLE001
                continue
        return page_h, out

    @staticmethod
    def _exclude_table_spans(
        spans: list[Span], fitz_tables: list[tuple], page_h: float
    ) -> list[Span]:
        """Rimuove gli span il cui centro cade dentro una regione tabellare."""
        if not fitz_tables:
            return spans
        pad = 2.5
        keep: list[Span] = []
        for s in spans:
            y = page_h - s.y  # coordinate PyMuPDF (origine in alto a sinistra)
            inside = any(
                box[0] - pad <= s.x <= box[2] + pad
                and box[1] - pad <= y <= box[3] + pad
                for box, _md in fitz_tables
            )
            if not inside:
                keep.append(s)
        return keep

    @staticmethod
    def _render_page(
        page_h: float,
        spans: list[Span],
        table_rows: set[int],
        fitz_tables: list[tuple],
    ) -> str:
        """Ricostruisce il flusso della pagina in ordine di lettura: righe di
        testo (euristica) e tabelle Markdown (PyMuPDF o euristica) alternate
        per posizione verticale."""
        from .tables import spans_to_rows

        rows = spans_to_rows(spans)
        blocks: list[tuple[float, str]] = []
        i, n = 0, len(rows)
        while i < n:
            if i in table_rows:
                j = i
                while j in table_rows and j < n:
                    j += 1
                grid = [[s.text for s in r.spans] for r in rows[i:j]]
                blocks.append((page_h - rows[i].y, _grid_to_markdown(grid)))
                i = j
            else:
                blocks.append((page_h - rows[i].y, " ".join(s.text for s in rows[i].spans)))
                i += 1
        for box, md in fitz_tables:
            blocks.append((float(box[1]), md))
        blocks.sort(key=lambda b: b[0])
        return "\n".join(t for _, t in blocks if t)

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
            title=tmp.stem.replace("_", " ").replace("-", " ").title(),
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
