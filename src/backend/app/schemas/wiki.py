"""Contratti di formato delle note compilate (Skill §3).

Schema Frontmatter YAML, struttura rigida del corpo e risultati dei parser.
Lo schema è indipendente dal modello AI: il compilatore deterministico e, in
futuro, i compilatori basati su LLM producono tutti lo stesso contratto.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

NOTE_TYPES = ("concept", "entity", "dataset", "synthesis")

# Blocchi obbligatori nel corpo di ogni nota atomica (Skill §3.2).
REQUIRED_SECTIONS = (
    "Sintesi Esecutiva",
    "Formalizzazione & Dettagli",
    "Relazioni nel Grafo",
    "Discrepanze & Limiti",
)


class NoteRelations(BaseModel):
    prerequisites: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)


class WikiNote(BaseModel):
    """Frontmatter YAML standardizzato delle pagine compilate (Skill §3.1)."""

    title: str
    type: Literal["concept", "entity", "dataset", "synthesis"]
    created: date
    updated: date
    sources: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    relations: NoteRelations = Field(default_factory=NoteRelations)

    @field_validator("title")
    @classmethod
    def _title_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title non può essere vuoto")
        return v.strip()

    @field_validator("sources")
    @classmethod
    def _sources_are_wikilinks(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for s in v:
            s = s.strip()
            if s and not s.startswith("[["):
                s = f"[[{s}]]"
            if s:
                out.append(s)
        return out

    @classmethod
    def new(cls, title: str, type_: str, **kw: Any) -> "WikiNote":
        today = date.today().isoformat()
        return cls(
            title=title,
            type=type_,  # type: ignore[arg-type]
            created=today,
            updated=today,
            **kw,
        )


# ---------------------------------------------------------------------------
# Serializzazione frontmatter (ordine delle chiavi deterministico)
# ---------------------------------------------------------------------------

def frontmatter_to_yaml(note: WikiNote) -> str:
    data: dict[str, Any] = {
        "title": note.title,
        "type": note.type,
        "created": note.created.isoformat(),
        "updated": note.updated.isoformat(),
        "sources": list(note.sources),
        "aliases": list(note.aliases),
        "tags": list(note.tags),
        "relations": {
            "prerequisites": list(note.relations.prerequisites),
            "related": list(note.relations.related),
            "conflicts_with": list(note.relations.conflicts_with),
        },
    }
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return text.rstrip() + "\n"


def parse_frontmatter(raw: str) -> tuple[WikiNote, str]:
    """Scomponi il contenuto di una nota in (frontmatter validato, corpo)."""
    if not raw.startswith("---"):
        raise ValueError("Frontmatter YAML assente: la nota non valida WikiSchema")
    end = raw.find("\n---", 3)
    if end == -1:
        raise ValueError("Frontmatter YAML non chiuso")
    header = raw[3:end].strip()
    body = raw[end + 4 :].lstrip("\n")
    data = yaml.safe_load(header) or {}
    note = WikiNote.model_validate(data)
    return note, body


def render_note(note: WikiNote, body_md: str) -> str:
    return f"---\n{frontmatter_to_yaml(note)}---\n{body_md.lstrip()}"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Risultati dei parser multimodali (Skill §4, Pipeline A)
# ---------------------------------------------------------------------------

class ParsedTable(BaseModel):
    caption: str = ""
    header: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    """Markdown grezzo intermedio estratto da un documento sorgente."""

    source_path: str  # percorso relativo al vault, es. sources/papers/x.pdf
    kind: Literal["document"] = "document"
    title: str
    markdown: str
    headings: list[str] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    word_count: int = 0
    parser_name: str = "unknown"
    # Metadati di provenienza (es. frontmatter YAML dei documenti Markdown
    # prodotti da engine OCR esterni: source, engine, date, …)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("markdown", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> str:
        return v if isinstance(v, str) else ""


class ParsedImage(BaseModel):
    source_path: str
    kind: Literal["image"] = "image"
    title: str
    width: int = 0
    height: int = 0
    mode: str = ""
    format: str = ""
    size_bytes: int = 0
    description: str = ""  # testo descrittivo (OCR/Vision: adattatori futuri)
    parser_name: str = "pillow"
