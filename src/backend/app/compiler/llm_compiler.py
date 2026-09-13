"""Compilatore basato su LLM — stesso contratto di `DeterministicCompiler`.

Attivato SOLO quando un provider è configurato e raggiabile (chiave API /
Ollama raggiungibile). Senza configurazione, l'applicazione opera in modalità
deterministica offline: nessun modello AI è necessario o invocato.

Integrazione in un secondo momento:
1. `pip install` i package opzionali o avviare Ollama locale;
2. `LLM_PROVIDER=anthropic` (+ `ANTHROPIC_API_KEY`) in `.env`;
3. il factory del layer LLM restituisce il client e `build_compiler()`
   passa automaticamente a questo compilatore.
"""
from __future__ import annotations

import json
import logging

from ..core.vault import slugify
from ..parsers.dataset import DatasetProfile
from ..schemas.wiki import (
    NoteRelations,
    ParsedDocument,
    ParsedImage,
    WikiNote,
    frontmatter_to_yaml,
)
from .base import CompiledNote, CompilationResult, CompileContext
from .deterministic import DeterministicCompiler
from .prompts import SYSTEM_COMPILER, USER_COMPILER_TEMPLATE

log = logging.getLogger("llmwiki.compiler.llm")


class LLMCompiler:
    name = "llm"

    def __init__(self, llm: object, fallback: DeterministicCompiler | None = None) -> None:
        self._llm = llm
        self._fallback = fallback or DeterministicCompiler()

    # -- API del protocollo Compiler ---------------------------------------
    def compile_document(self, parsed: ParsedDocument, ctx: CompileContext) -> CompilationResult:
        result = self._llm_compile(parsed.source_path, parsed.title, parsed.markdown, ctx,
                                   default_dir="wiki/concepts")
        if result is None:
            log.warning("LLM non disponibile o output non valido: fallback deterministico")
            result = self._fallback.compile_document(parsed, ctx)
            result.messages.append("LLM non raggiungibile/output non valido: usata la sintesi deterministica.")
        return result

    def compile_dataset(self, profile: DatasetProfile, ctx: CompileContext) -> CompilationResult:
        # I dataset restano schede metadati anche con LLM (invariante §1.4).
        return self._fallback.compile_dataset(profile, ctx)

    def compile_image(self, meta: ParsedImage, ctx: CompileContext) -> CompilationResult:
        return self._fallback.compile_image(meta, ctx)

    # -- sintasi via LLM -----------------------------------------------------
    def _llm_compile(
        self,
        source_path: str,
        title: str,
        markdown: str,
        ctx: CompileContext,
        default_dir: str,
    ) -> CompilationResult | None:
        from ..index.index_builder import render_index_markdown  # per l'indice nel prompt

        index_txt = render_index_markdown(ctx.existing)
        prompt = USER_COMPILER_TEMPLATE.format(
            index=index_txt or "(vault vuoto)",
            source_path=source_path,
            title=title,
            markdown=markdown[:24000],
        )
        try:
            resp = self._llm.complete(prompt, system=SYSTEM_COMPILER, max_tokens=8192)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            log.error("LLM compile failure: %s", exc)
            return None
        payload = _parse_json_lenient(resp.text)
        if not payload or "notes" not in payload:
            return None
        result = CompilationResult(compiler=f"llm:{getattr(self._llm, 'name', 'llm')}")
        for item in payload["notes"][: ctx.max_concept_notes + 2]:
            try:
                note = _coerce_note(item, source_path, default_dir)
            except Exception as exc:  # noqa: BLE001
                result.messages.append(f"Nota scartata (schema): {exc}")
                continue
            body = str(item.get("body_md", "")).strip() or "(corpo non fornito)"
            if not body.startswith("#"):
                body = f"# {note.title}\n\n{body}"
            result.notes.append(CompiledNote(
                rel_path=note_rel_path(item, note, default_dir),
                frontmatter_yaml=frontmatter_to_yaml(note),
                body_md=body + "\n",
            ))
        if not result.notes:
            return None
        return result


def _parse_json_lenient(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _coerce_note(item: dict, source_path: str, default_dir: str) -> WikiNote:
    from datetime import date

    today = date.today().isoformat()
    relations_raw = item.get("relations") or {}
    relations = NoteRelations(
        prerequisites=list(relations_raw.get("prerequisites", [])),
        related=list(relations_raw.get("related", [])),
        conflicts_with=list(relations_raw.get("conflicts_with", [])),
    )
    sources = list(item.get("sources", [])) or [f"[[{source_path}]]"]
    return WikiNote(
        title=str(item.get("title") or "Senza titolo"),
        type=item.get("type", "concept") if item.get("type") in ("concept", "entity", "dataset", "synthesis") else "concept",
        created=today,
        updated=today,
        sources=sources,
        aliases=[str(a) for a in item.get("aliases", [])],
        tags=[str(t) for t in item.get("tags", [])],
        relations=relations,
    )


def note_rel_path(item: dict, note: WikiNote, default_dir: str) -> str:
    rel = str(item.get("rel_path", "")).strip()
    if rel.startswith("wiki/") and rel.endswith(".md"):
        return rel
    folder = "wiki/entities" if note.type in ("entity", "dataset") else default_dir
    return f"{folder}/{slugify(note.title)}.md"
