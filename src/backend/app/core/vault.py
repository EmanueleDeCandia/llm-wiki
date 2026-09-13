"""Gestione del vault locale: topologia, apertura, invarianze (Skill §1-§2).

Invarianti fondamentali applicate qui:
* `sources/` è immutabile per l'applicazione e per eventuali agenti AI:
  l'unica sotto-cartella gestita dall'app è `sources/images/generated/`
  (output delle esecuzioni sandbox, esplicitamente previsto dalla Skill §4-C).
  Ogni hash SHA-256 dei file sorgenti originali viene verificato dopo ogni
  pipeline e qualsiasi divergenza viene riportata all'utente.
* Le note di `wiki/` e i metadati di `_index/` sono le uniche superfici
  scrivibili dell'engine.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

VAULT_DIRS = (
    "sources/papers",
    "sources/images",
    "sources/images/generated",
    "sources/datasets",
    "wiki/concepts",
    "wiki/entities",
    "wiki/synthesis",
    "_index",
    "scripts/generated",
)

# Cartelle sotto sources/ che l'app è autorizzata a scrivere (Skill §4-C, punto 4).
GENERATED_SOURCE_DIRS = ("sources/images/generated",)

WIKILINK_SAFE = re.compile(r"[^\w/\-. ]")


def slugify(text: str, max_len: int = 60) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    if not text:
        text = "nota"
    return text[:max_len].rstrip("-")


def safe_filename(name: str) -> str:
    base = Path(name).name
    base = base.replace("\x00", "")
    return base or "file"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Vault:
    """Stato in memoria del vault attualmente aperto."""

    root: Path
    template_root: Path | None = None
    _source_hashes: dict[str, str] = field(default_factory=dict)

    # -- percorsi ----------------------------------------------------------
    @property
    def sources(self) -> Path:
        return self.root / "sources"

    @property
    def wiki(self) -> Path:
        return self.root / "wiki"

    @property
    def index_dir(self) -> Path:
        return self.root / "_index"

    @property
    def index_md(self) -> Path:
        return self.index_dir / "INDEX.md"

    @property
    def graph_json(self) -> Path:
        return self.index_dir / "graph.json"

    @property
    def lint_report(self) -> Path:
        return self.index_dir / "lint_report.md"

    @property
    def scripts_dir(self) -> Path:
        return self.root / "scripts"

    @property
    def generated_scripts(self) -> Path:
        return self.scripts_dir / "generated"

    @property
    def generated_images(self) -> Path:
        return self.sources / "images" / "generated"

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def abs(self, rel: str) -> Path:
        return (self.root / rel).resolve()

    # -- topologia ---------------------------------------------------------
    def ensure_topology(self) -> list[str]:
        """Crea le cartelle mancanti della topologia obbligatoria (Skill §2)."""
        created: list[str] = []
        for d in VAULT_DIRS:
            p = self.root / d
            if not p.is_dir():
                p.mkdir(parents=True, exist_ok=True)
                created.append(d)
        self._seed_vault_files()
        return created

    def _seed_vault_files(self) -> None:
        """Copia CLAUDE.md / sandbox_runner.py dal vault_template se assenti."""
        seeds: dict[str, str] = {
            "CLAUDE.md": "CLAUDE.md",
            "scripts/sandbox_runner.py": "scripts/sandbox_runner.py",
        }
        if not self.template_root:
            return
        for rel, template_name in seeds.items():
            target = self.root / rel
            if target.exists():
                continue
            src = self.template_root / template_name
            if src.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, target)

    def validate_tree(self) -> list[str]:
        """Verifica la presenza della topologia; restituisce le parti mancanti."""
        missing = []
        for d in VAULT_DIRS:
            if not (self.root / d).is_dir():
                missing.append(d)
        return missing

    # -- immutabilità delle sorgenti (Skill §1.2) ---------------------------
    def snapshot_sources(self) -> dict[str, str]:
        """Fotografa gli hash dei file sorgenti (escluse le cartelle generate)."""
        self._source_hashes = {}
        for p in sorted(self.sources.rglob("*")):
            if not p.is_file():
                continue
            if self._is_generated_output(p):
                continue
            self._source_hashes[self.rel(p)] = sha256_file(p)
        return self._source_hashes

    def verify_sources(self) -> list[str]:
        """Controllo di invarianza: restituisce i file sorgenti alterati."""
        altered: list[str] = []
        current = self.snapshot_sources()
        for rel, digest in self._source_hashes.items():
            new = current.get(rel)
            if new != digest:
                altered.append(rel)
        return altered

    def _is_generated_output(self, path: Path) -> bool:
        rel = self.rel(path)
        return any(rel.startswith(d + "/") for d in GENERATED_SOURCE_DIRS)

    def store_source(self, filename: str, data: bytes, branch: str) -> Path:
        """Salva un file in sources/<branch>/ senza sovrascrivere mai.

        Se un file omonimo identico (stessi byte) è già presente — ad es.
        posizionato via file-watcher — viene riusato: nessuna duplicazione.
        """
        target_dir = self.root / "sources" / branch
        target_dir.mkdir(parents=True, exist_ok=True)
        name = safe_filename(filename)
        candidate = target_dir / name
        if candidate.is_file() and candidate.read_bytes() == data:
            return candidate
        stem, suffix = Path(name).stem, Path(name).suffix
        i = 2
        while candidate.exists():
            candidate = target_dir / f"{stem}_{i}{suffix}"
            i += 1
        candidate.write_bytes(data)
        return candidate
