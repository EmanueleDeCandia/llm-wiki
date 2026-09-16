"""Test dell'adattatore OCR HTTP (engine VLM locali) con server mock.

Simula il contratto `POST /parse → {"markdown": …}` di un servizio che
esegue un VLM (dots.mocr / DeepSeek-OCR-2) su GPU.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.parsers.ocr_http import OcrHttpClient, OcrHttpError
from app.parsers.pdf_doc import PdfParser

from .conftest import build_scanned_pdf, build_simple_pdf

OCR_MD = """# Contratto di appalto

Rep. 42/2026 — fornitura di arredi.

## Art. 1 Oggetto

Il presente contratto ha ad oggetto la fornitura di arredi.

| Voce | Importo |
| --- | --- |
| Arredi | 12000.00 |
| Trasporto | 800.00 |
"""


class _Handler(BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/parse":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        _ = self.rfile.read(length)
        _Handler.hits.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"markdown": OCR_MD}).encode("utf-8"))

    def log_message(self, *args) -> None:  # silenzio
        pass


@pytest.fixture()
def ocr_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_ocr_client_parses_markdown_and_tables(ocr_server: str) -> None:
    client = OcrHttpClient(base_url=ocr_server)
    assert client.is_configured()
    doc = client.parse_pdf(b"%PDF-1.4 fake", "contratto.pdf", "sources/papers/contratto.pdf")
    assert doc.parser_name == "pdf:ocr-http"
    assert "Contratto di appalto" in doc.markdown
    assert doc.title == "Contratto di appalto"
    assert len(doc.tables) == 1
    assert doc.tables[0].header == ["Voce", "Importo"]
    assert doc.tables[0].rows[0] == ["Arredi", "12000.00"]


def test_forced_engine_dotsmocr(monkeypatch, ocr_server: str, tmp_path: Path) -> None:
    monkeypatch.setenv("LLW_OCR_HTTP_URL", ocr_server)
    p = tmp_path / "scansione.pdf"
    build_scanned_pdf(p)
    parsed = PdfParser(engine="dotsmocr").parse(p, "sources/papers/scansione.pdf")
    assert "arredi" in parsed.markdown.lower()
    assert parsed.parser_name == "pdf:dotsmocr-http"
    assert len(parsed.tables) == 1


def test_forced_engine_deepseek2(monkeypatch, ocr_server: str, tmp_path: Path) -> None:
    monkeypatch.setenv("LLW_OCR_HTTP_URL", ocr_server)
    p = tmp_path / "scansione.pdf"
    build_scanned_pdf(p)
    parsed = PdfParser(engine="deepseek2").parse(p, "sources/papers/scansione.pdf")
    assert parsed.parser_name == "pdf:deepseek2-http"


def test_ocr_not_configured_raises(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LLW_OCR_HTTP_URL", raising=False)
    p = tmp_path / "x.pdf"
    build_scanned_pdf(p)
    with pytest.raises(OcrHttpError):
        PdfParser(engine="deepseek2").parse(p, "sources/papers/x.pdf")


def test_auto_dense_text_layer_keeps_builtin(monkeypatch, ocr_server: str, tmp_path: Path) -> None:
    """PDF born-digital con layer denso: il VLM NON viene chiamato."""
    monkeypatch.setenv("LLW_OCR_HTTP_URL", ocr_server)
    _Handler.hits.clear()
    p = tmp_path / "born_digital.pdf"
    build_simple_pdf(
        ["Transformer paper with a long enough text layer for density check"] * 4,
        p,
    )
    parsed = PdfParser(engine="auto").parse(p, "sources/papers/born_digital.pdf")
    assert _Handler.hits == []
    assert parsed.parser_name.startswith("pdf:pypdf") or parsed.parser_name.startswith("pdf:pymupdf")
    assert "Transformer paper" in parsed.markdown


def test_auto_sparse_text_layer_escalates_to_ocr(monkeypatch, ocr_server: str, tmp_path: Path) -> None:
    """PDF senza layer testuale (scansione): auto escala al VLM HTTP."""
    monkeypatch.setenv("LLW_OCR_HTTP_URL", ocr_server)
    _Handler.hits.clear()
    p = tmp_path / "scansione.pdf"
    build_scanned_pdf(p)
    parsed = PdfParser(engine="auto").parse(p, "sources/papers/scansione.pdf")
    assert _Handler.hits == ["/parse"]
    assert "arredi" in parsed.markdown.lower()
    assert parsed.parser_name.endswith("-http")


def test_auto_ocr_failure_falls_back_to_builtin(monkeypatch, tmp_path: Path) -> None:
    """Servizio OCR irraggiungibile: auto degrada al built-in (nessuna eccezione)."""
    monkeypatch.setenv("LLW_OCR_HTTP_URL", "http://127.0.0.1:1")  # porta chiusa
    p = tmp_path / "scansione.pdf"
    build_scanned_pdf(p)
    parsed = PdfParser(engine="auto").parse(p, "sources/papers/scansione.pdf")
    # built-in su PDF solo-immagine: markdown vuoto o minimale, ma nessuna raise
    assert parsed.parser_name.startswith("pdf:")
