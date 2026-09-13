"""Parser immagini (Pillow).

Produce metadati tecnici + un segnaposto per la descrizione OCR/Vision:
quando un modello Vision verrà integrato, basterà registrare un
`VisionExtractor` nel registro — il contratto `ParsedImage` non cambia.
"""
from __future__ import annotations

from pathlib import Path

from ..schemas.wiki import ParsedImage


class ImageParser:
    name = "image"

    def parse(self, path: Path, vault_rel: str) -> ParsedImage:
        from PIL import Image

        with Image.open(path) as im:
            meta = ParsedImage(
                source_path=vault_rel,
                title=path.stem.replace("_", " ").replace("-", " ").title(),
                width=im.width,
                height=im.height,
                mode=im.mode,
                format=im.format or path.suffix.lstrip(".").upper(),
                size_bytes=path.stat().st_size,
                description=(
                    "Descrizione testuale in attesa: configurare un estrattore "
                    "Vision/OCR (adattatore opzionale) per compilare il contenuto "
                    "di schemi, diagrammi o tabelle raster."
                ),
                parser_name=self.name,
            )
        return meta
