"""Registro dei parser: smistamento per estensione (Skill §4-A)."""
from __future__ import annotations

from pathlib import Path

from .dataset import DatasetParser, DatasetProfile
from .image_doc import ImageParser
from .pdf_doc import PdfParser
from .text_doc import DocxDocumentParser, TextDocumentParser

DOCUMENT_EXTENSIONS = {
    ".pdf": "papers",
    ".epub": "papers",
    ".txt": "papers",
    ".md": "papers",
    ".markdown": "papers",
    ".docx": "papers",
    ".doc": "papers",
}
IMAGE_EXTENSIONS = {
    ".png": "images",
    ".jpg": "images",
    ".jpeg": "images",
    ".webp": "images",
    ".gif": "images",
    ".bmp": "images",
}
DATASET_EXTENSIONS = {
    ".csv": "datasets",
    ".tsv": "datasets",
    ".parquet": "datasets",
    ".sqlite": "datasets",
    ".db": "datasets",
    ".sqlite3": "datasets",
}


def branch_for_extension(suffix: str) -> str | None:
    s = suffix.lower()
    if s in DOCUMENT_EXTENSIONS:
        return DOCUMENT_EXTENSIONS[s]
    if s in IMAGE_EXTENSIONS:
        return IMAGE_EXTENSIONS[s]
    if s in DATASET_EXTENSIONS:
        return DATASET_EXTENSIONS[s]
    return None


class ParserRegistry:
    """Smista i file di `sources/` al parser corretto.

    Adattatori opzionali (docling/marker/OCR) si attivano tramite env
    senza toccare questa classe: i contratti di output restano identici.
    """

    def __init__(self) -> None:
        self.text = TextDocumentParser()
        self.docx = DocxDocumentParser()
        self.pdf = PdfParser()
        self.image = ImageParser()
        self.dataset = DatasetParser()

    def branch(self, suffix: str) -> str | None:
        return branch_for_extension(suffix)

    def parse_document(self, path: Path, vault_rel: str, image_map: dict[str, str] | None = None):
        s = path.suffix.lower()
        if s == ".pdf":
            return self.pdf.parse(path, vault_rel)
        if s in (".docx", ".doc"):
            return self.docx.parse(path, vault_rel)
        return self.text.parse(path, vault_rel, image_map=image_map)

    def parse_image(self, path: Path, vault_rel: str):
        return self.image.parse(path, vault_rel)

    def parse_dataset(self, path: Path, vault_rel: str) -> DatasetProfile:
        return self.dataset.profile(path, vault_rel)
