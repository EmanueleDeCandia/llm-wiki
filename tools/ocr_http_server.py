#!/usr/bin/env python3
"""Server di riferimento per l'engine OCR HTTP di LLM Wiki (Livello B).

Espone il contratto atteso da `LLW_OCR_HTTP_URL`:

    POST /parse   (multipart/form-data, campo "file" = PDF; campo opzionale "model")
    → 200 {"markdown": "…"}

Implementazione di riferimento con **DeepSeek-OCR-2** (transformers, GPU).
Da eseguire sulla macchina con la GPU, NON dentro l'app:

    pip install fastapi "uvicorn[standard]" pymupdf torch transformers
    python tools/ocr_http_server.py --model deepseek-ai/DeepSeek-OCR-2 --port 8700

Poi nel `.env` del sidecar:

    LLW_PDF_ENGINE=dotsmocr-http   (o deepseek2-http / ocr-http)
    LLW_OCR_HTTP_URL=http://SUA-MACCHINA:8700

Per **dots.mocr**: il modello ha la stessa famiglia di prompt/output
(Markdown). Sostituire il blocco di inferenza `_infer_page` con l'API del
modello dots.mocr (repo studio-dots-ai/dots.ocr: vLLM o transformers); il
resto del server (PDF→pagine, contratto HTTP, concatenazione) è identico.

AVVERTENZA: il blocco inferenza GPU non è testabile in un ambiente senza
GPU/HuggingFace — validare su macchina reale prima dell'uso in produzione.
Il contratto HTTP e il client (app/parsers/ocr_http.py) sono testati.
"""
from __future__ import annotations

import argparse
import io
import logging
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

log = logging.getLogger("ocr_http_server")

app = FastAPI(title="LLM Wiki OCR HTTP (reference)")

_STATE: dict = {"model": None, "tokenizer": None, "model_name": ""}


def _load(model_name: str) -> None:
    import torch
    from transformers import AutoModel, AutoTokenizer

    log.info("caricamento modello %s …", model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_name,
        _attn_implementation="flash_attention_2",
        trust_remote_code=True,
        use_safetensors=True,
    )
    model = model.eval().cuda().to(torch.bfloat16)
    _STATE["model"], _STATE["tokenizer"], _STATE["model_name"] = model, tokenizer, model_name
    log.info("modello pronto.")


def _pdf_to_pages(data: bytes, dpi: int = 144) -> list[bytes]:
    """PDF → immagini PNG delle pagine (PyMuPDF)."""
    import pymupdf as fitz

    doc = fitz.open(stream=data, filetype="pdf")
    zoom = dpi / 72.0
    pages: list[bytes] = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pages.append(pix.tobytes("png"))
    return pages


def _infer_page(png: bytes, model_name: str | None = None) -> str:
    """Una pagina → Markdown (prompt ufficiale DeepSeek-OCR-2)."""
    name = model_name or _STATE["model_name"]
    if name != _STATE["model_name"]:
        raise HTTPException(status_code=400, detail=f"modello non caricato: {name}")
    with tempfile.TemporaryDirectory() as td:
        img_path = Path(td) / "page.png"
        img_path.write_bytes(png)
        out_dir = Path(td) / "out"
        prompt = "<image>\n<|grounding|>Convert the document to markdown. "
        res = _STATE["model"].infer(
            _STATE["tokenizer"],
            prompt=prompt,
            image_file=str(img_path),
            output_path=str(out_dir),
            base_size=1024,
            image_size=768,
            crop_mode=True,
            save_results=True,
        )
    text = res if isinstance(res, str) else ""
    if not text.strip():
        # alcuni build salvano l'output su disco senza restituirlo
        for f in sorted(out_dir.glob("*.md")) + sorted(out_dir.glob("*.txt")):
            text = f.read_text(encoding="utf-8", errors="replace")
            if text.strip():
                break
    return text


@app.post("/parse")
async def parse(
    file: UploadFile = File(...),
    model: str = Form(default=""),
) -> dict:
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=415, detail="atteso un PDF (intestazione %PDF)")
    try:
        pages = _pdf_to_pages(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"PDF non leggibile: {exc}") from exc
    if not pages:
        raise HTTPException(status_code=422, detail="PDF senza pagine")

    parts: list[str] = []
    for i, png in enumerate(pages):
        try:
            md = _infer_page(png, model or None)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"inferenza pagina {i+1} fallita: {exc}")
        if md.strip():
            parts.append(md.strip())
        log.info("pagina %d/%d → %d caratteri", i + 1, len(pages), len(md))
    markdown = "\n\n".join(parts)
    if not markdown.strip():
        raise HTTPException(status_code=502, detail="il modello non ha prodotto testo")
    return {"markdown": markdown, "pages": len(pages), "file": file.filename or ""}


@app.get("/health")
def health() -> dict:
    return {
        "ok": _STATE["model"] is not None,
        "model": _STATE["model_name"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek-ai/DeepSeek-OCR-2")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8700)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    _load(args.model)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
