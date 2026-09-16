"""Orchestratore delle pipeline (Skill §4).

Pipeline A — IngestAndCompile:
  sources/ (nuovo file) → parser multimodale → compilatore (deterministico |
  LLM) → scrittura note in wiki/ → rigenerazione INDEX.md + graph.json →
  verifica invarianza delle sorgenti (hash SHA-256).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from .compiler.base import CompilationResult, CompileContext
from .compiler.links import LinkRegistry
from .core.config import settings
from .core.vault import Vault
from .index.index_builder import build_registry, write_indexes
from .llm.factory import get_llm_client
from .parsers.registry import ParserRegistry
from .schemas.wiki import ParsedDocument

log = logging.getLogger("llmwiki.pipeline")


@dataclass
class IngestResult:
    source_path: str
    branch: str
    parser: str = ""
    compiler: str = ""
    notes_created: list[str] = field(default_factory=list)
    notes_skipped: list[str] = field(default_factory=list)
    index_updated: bool = False
    sources_integrity_ok: bool = True
    sources_altered: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def _existing_names(reg: LinkRegistry, exclude: set[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for node in reg.nodes.values():
        if node.type == "source" or node.id in exclude:
            continue
        out[node.id] = [node.title, *node.aliases]
    return out


def ingest_file(
    vault: Vault,
    file_path: Path,
    branch: str,
    image_map: dict[str, str] | None = None,
    export_tables: bool | None = None,
) -> IngestResult:
    vault.snapshot_sources()
    registry = ParserRegistry()
    source_rel = vault.rel(file_path)
    result = IngestResult(source_path=source_rel, branch=branch, parser="")

    reg = build_registry(vault)
    ctx = CompileContext(
        existing=_existing_names(reg, set()),
        llm=get_llm_client(),
        max_concept_notes=settings.max_concept_notes_per_source,
    )

    from .compiler.deterministic import DeterministicCompiler
    from .compiler.llm_compiler import LLMCompiler
    from .llm.deterministic import OfflineLLMClient

    llm = ctx.llm
    compiler = LLMCompiler(llm) if not isinstance(llm, OfflineLLMClient) else DeterministicCompiler()

    parsed_doc: ParsedDocument | None = None
    if branch == "papers":
        parsed_doc = registry.parse_document(file_path, source_rel, image_map=image_map)
        parsed = parsed_doc
        result.parser = parsed.parser_name
        comp: CompilationResult = compiler.compile_document(parsed, ctx)
    elif branch == "images":
        meta = registry.parse_image(file_path, source_rel)
        result.parser = meta.parser_name
        comp = compiler.compile_image(meta, ctx)
    else:  # datasets
        profile = registry.parse_dataset(file_path, source_rel)
        result.parser = profile.engine
        comp = compiler.compile_dataset(profile, ctx)

    result.compiler = comp.compiler
    result.messages.extend(comp.messages)

    # Scrittura delle note: mai sovrascrittura di note esistenti (idempotenza).
    for note in comp.notes:
        target = vault.root / note.rel_path
        if target.exists():
            result.notes_skipped.append(note.rel_path)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        from .schemas.wiki import render_note, WikiNote, parse_frontmatter

        # Rivalidazione del contratto prima della scrittura (difesa in profondità).
        try:
            parsed_note, _body = parse_frontmatter(
                f"---\n{note.frontmatter_yaml}---\n{note.body_md}"
            )
            assert parsed_note.title
        except Exception as exc:  # noqa: BLE001
            result.messages.append(f"Nota non valida scartata ({note.rel_path}): {exc}")
            continue
        target.write_text(f"---\n{note.frontmatter_yaml}---\n{note.body_md}", encoding="utf-8")
        result.notes_created.append(note.rel_path)

    # Rigenerazione indice e grafo.
    if result.notes_created:
        write_indexes(vault)
        result.index_updated = True

    # Invarianza delle sorgenti (Skill §1.2).
    altered = vault.verify_sources()
    result.sources_altered = altered
    result.sources_integrity_ok = not altered
    if altered:
        result.messages.append(f"INTEGRITÀ: file sorgenti alterati: {altered}")

    # Dati derivati: le tabelle estratte da un documento (PDF, Markdown OCR,
    # DOCX…) diventano dataset .tsv in sources/datasets/ e vengono ingesti
    # come dataset veri — così lo Sandbox le analizza con gli stessi
    # template dei CSV/Parquet. Disattivabile: LLW_EXPORT_TABLE_DATASETS=0.
    if branch == "papers" and parsed_doc is not None:
        result.messages.extend(_export_table_datasets(vault, parsed_doc, result, export_tables))

    return result


def _export_table_datasets(
    vault: Vault,
    parsed: ParsedDocument,
    result: IngestResult,
    export_tables: bool | None,
) -> list[str]:
    """Esporta le tabelle significative come .tsv e le ingeste (idempotente)."""
    if export_tables is None:
        export_tables = os.environ.get("LLW_EXPORT_TABLE_DATASETS", "1") != "0"
    if not export_tables:
        return []
    msgs: list[str] = []
    stem = Path(parsed.source_path).stem
    for i, t in enumerate(parsed.tables, start=1):
        if len(t.header) < 2 or len(t.rows) < 2:
            continue
        tsv_rel = f"sources/datasets/{stem}_tabella_{i}.tsv"
        tsv_path = vault.root / tsv_rel
        lines = ["\t".join(t.header), *("\t".join(r) for r in t.rows)]
        content = "\n".join(lines) + "\n"
        if tsv_path.is_file() and tsv_path.read_text(encoding="utf-8") == content:
            continue  # già presente e identico
        tsv_path.parent.mkdir(parents=True, exist_ok=True)
        tsv_path.write_text(content, encoding="utf-8")
        sub = ingest_file(vault, tsv_path, "datasets", export_tables=False)
        result.notes_created.extend(sub.notes_created)
        result.messages.extend(sub.messages)
        msgs.append(f"Tabella {i} ({len(t.rows)} righe) → dataset {tsv_rel}")
    return msgs
