"""Contratto dei parser multimodali (Skill §4, Pipeline A).

Ogni formato di sorgente ha un `DocumentParser`; il `ParserRegistry` smista
in base all'estensione. I parser producono sempre il *Markdown grezzo
intermedio* (o un profilo dati per i dataset) che il compilatore trasforma
in note atomiche: il contratto è lo stesso per il parser leggero built-in e
per gli adattatori opzionali ad alta fedeltà (docling/marker) integrabili in
un secondo momento.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..schemas.wiki import ParsedDocument, ParsedImage


class ParseResult:
    """Risultato unificato di un parser: documento, immagine o profilo dataset."""


class DocumentParser(Protocol):
    name: str

    def parse(self, path: Path, vault_rel: str) -> ParsedDocument: ...


class ImageParser(Protocol):
    name: str

    def parse(self, path: Path, vault_rel: str) -> ParsedImage: ...


class DatasetParser(Protocol):
    name: str

    def profile(self, path: Path, vault_rel: str) -> "object": ...


__all__ = ["DocumentParser", "ImageParser", "DatasetParser", "ParseResult"]
