"""Contratto del compilatore (Skill §2 invarianti + §4-A.4).

Il compilatore trasforma l'estratto grezzo in **note atomiche** con
frontmatter YAML valido e corpo a blocchi rigidi. L'applicazione funziona
completamente senza modelli AI (`DeterministicCompiler`); quando un provider
LLM verrà configurato, `LLMCompiler` (stesso contratto) sostituisce la
componente di sintesi mantenendo invariate provenance, schema e grafo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from ..parsers.dataset import DatasetProfile
from ..schemas.wiki import ParsedDocument, ParsedImage


@dataclass
class CompiledNote:
    rel_path: str  # es. wiki/concepts/attention-mechanism.md
    frontmatter_yaml: str
    body_md: str


@dataclass
class CompilationResult:
    notes: list[CompiledNote] = field(default_factory=list)
    compiler: str = "deterministic"
    messages: list[str] = field(default_factory=list)


class Compiler(Protocol):
    """Interfaccia di compilazione: i due implementatori (deterministico e
    LLM) sono intercambiabili senza toccare pipeline, indice o UI."""

    @property
    def name(self) -> str: ...

    def compile_document(
        self, parsed: ParsedDocument, ctx: "CompileContext"
    ) -> CompilationResult: ...

    def compile_dataset(
        self, profile: DatasetProfile, ctx: "CompileContext"
    ) -> CompilationResult: ...

    def compile_image(
        self, meta: ParsedImage, ctx: "CompileContext"
    ) -> CompilationResult: ...


@dataclass
class CompileContext:
    """Contesto immutabile passato a ogni compilazione: indice esistente,
    client LLM (opzionale) e limiti configurativi."""

    existing: dict[str, list[str]] = field(default_factory=dict)  # node_id -> [title, *aliases]
    llm: Optional[object] = None  # llm.base.LLMClient | None (Skill §5.2)
    max_concept_notes: int = 12
