"""Endpoint API — contratto Skill §6 + endpoint di supporto per la UI."""
from __future__ import annotations

import base64
import mimetypes
import re
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..agent.query_service import run_query
from ..compiler.links import LinkRegistry, strip_links
from ..core.config import settings
from ..core.state import AppState
from ..core.vault import Vault, slugify
from ..index.index_builder import build_graph, build_registry, write_indexes
from ..lint.lint_engine import load_lint_report, run_lint, write_lint_report
from ..llm.factory import get_llm_client, llm_status
from ..pipeline import ingest_file
from ..sandbox.kernel_manager import create_kernel
from ..schemas.wiki import (
    NOTE_TYPES,
    REQUIRED_SECTIONS,
    WikiNote,
    parse_frontmatter,
    render_note,
)

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Modelli di richiesta/risposta
# ---------------------------------------------------------------------------

class VaultOpenRequest(BaseModel):
    path: str = Field(description="Percorso assoluto del vault locale")
    template_root: str | None = None
    create_if_missing: bool = True


class VaultOpenResponse(BaseModel):
    root: str
    created_dirs: list[str]
    missing_before: list[str]
    index_initialized: bool
    llm_status: dict


class IngestResponse(BaseModel):
    source_path: str
    branch: str
    parser: str
    compiler: str
    notes_created: list[str]
    notes_skipped: list[str]
    index_updated: bool
    sources_integrity_ok: bool
    sources_altered: list[str]
    messages: list[str]


class SandboxRunRequest(BaseModel):
    code: str = Field(description="Codice Python autonomo")
    task_name: str | None = None
    dataset: str | None = Field(
        default=None,
        description="Percorso relativo a sources/ del dataset (es. datasets/vendite.csv)",
    )
    synthesize: bool = Field(
        default=False,
        description="Dopo l'esecuzione, compila una nota in wiki/synthesis/ (Pipeline C.5)",
    )


class SandboxFigure(BaseModel):
    name: str
    path: str
    size_bytes: int
    data_url: str


class SandboxRunResponse(BaseModel):
    task_id: str
    script_path: str
    exit_code: int | None
    ok: bool
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    error: str | None
    figures: list[SandboxFigure]
    synthesis_note: str | None = None


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5


class QueryResponse(BaseModel):
    provider: str
    answer_markdown: str
    citations: list[dict]


class NoteSaveRequest(BaseModel):
    content: str = Field(description="Contenuto completo della nota (frontmatter + corpo)")


# ---------------------------------------------------------------------------
# Utilità
# ---------------------------------------------------------------------------

def _state() -> AppState:
    from ..main import state

    return state


def _vault() -> Vault:
    return _state().require_vault()


def _resolve_vault_path(rel: str) -> Path:
    vault = _vault()
    p = vault.abs(rel)
    if vault.root.resolve() not in p.parents and p != vault.root.resolve():
        raise HTTPException(status_code=400, detail="Percorso fuori dal vault")
    return p


# ---------------------------------------------------------------------------
# Skill §6 — endpoint vincolanti
# ---------------------------------------------------------------------------

@router.post("/vault/open", response_model=VaultOpenResponse)
def vault_open(req: VaultOpenRequest) -> VaultOpenResponse:
    from ..main import state

    root = Path(req.path).expanduser().resolve()
    if not root.exists() and not req.create_if_missing:
        raise HTTPException(status_code=404, detail=f"Path inesistente: {root}")
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise HTTPException(status_code=400, detail="Il path indicato non è una directory")

    template_root = Path(req.template_root).expanduser().resolve() if req.template_root else None
    if template_root and not template_root.is_dir():
        template_root = None

    vault = Vault(root=root, template_root=template_root)
    missing = vault.validate_tree()
    created = vault.ensure_topology()
    index_initialized = False
    if not vault.index_md.exists() or not vault.graph_json.exists():
        write_indexes(vault)
        index_initialized = True
    vault.snapshot_sources()

    state.vault = vault
    state.opened_at = time.time()
    return VaultOpenResponse(
        root=str(root),
        created_dirs=created,
        missing_before=missing,
        index_initialized=index_initialized,
        llm_status=_llm_dict(),
    )


def _llm_dict() -> dict:
    s = llm_status()
    return {
        "provider": s.provider,
        "model": s.model,
        "configured": s.configured,
        "reachable": s.reachable,
        "description": s.description,
    }


@router.post("/ingest/file", response_model=IngestResponse)
async def ingest_file_endpoint(file: UploadFile = File(...),
                               branch: str | None = Query(default=None)) -> IngestResponse:
    from ..parsers.registry import ParserRegistry

    vault = _vault()
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File vuoto")
    suffix = Path(file.filename or "senza_nome.bin").suffix.lower()
    detected = ParserRegistry().branch(suffix) if not branch else None
    target = (branch or detected)
    if not target:
        raise HTTPException(
            status_code=415,
            detail=f"Estensione non supportata '{suffix}'. "
                   f"Supportate: documenti (pdf, epub, txt, md, docx), "
                   f"immagini (png, jpg, webp…), dataset (csv, tsv, parquet, sqlite)",
        )
    stored = vault.store_source(file.filename or "file", data, target)
    res = ingest_file(vault, stored, target)
    return IngestResponse(**res.__dict__)


@router.get("/graph/nodes")
def graph_nodes() -> dict:
    """Adiacenze {V, E} per il rendering del grafo (Skill §6)."""
    vault = _vault()
    reg = build_registry(vault)
    return build_graph(vault, reg)


@router.post("/lint/run")
def lint_run() -> dict:
    """Pipeline B: audit semantico + aggiornamento lint_report.md (Skill §6)."""
    vault = _vault()
    result = write_lint_report(vault)
    write_indexes(vault)  # coerente: il grafo cache riflette lo stato corrente
    return {
        "ok": True,
        "clean": result.clean,
        "node_count": result.node_count,
        "edge_count": result.edge_count,
        "orphan_links": result.orphan_links,
        "isolated_nodes": result.isolated_nodes,
        "components": len(result.components),
        "conflicts": result.conflicts,
        "structural_issues": result.structural_issues,
        "provenance_missing": result.provenance_missing,
        "report_path": "_index/lint_report.md",
    }


@router.post("/sandbox/run", response_model=SandboxRunResponse)
def sandbox_run(req: SandboxRunRequest) -> SandboxRunResponse:
    """Pipeline C: esecuzione Python isolata, 30s, stdout/stderr + figure."""
    vault = _vault()
    dataset_rel = None
    if req.dataset:
        dataset_rel = _validate_dataset_path(req.dataset)
    kernel = create_kernel(vault, timeout=settings.sandbox_timeout_seconds,
                           python=settings.sandbox_python)
    result = kernel.run(req.code, task_name=req.task_name, dataset_rel=dataset_rel)

    synthesis_note: str | None = None
    if req.synthesize and result.ok:
        synthesis_note = _build_synthesis_note(vault, req, result)

    return SandboxRunResponse(
        task_id=result.task_id,
        script_path=result.script_path,
        exit_code=result.exit_code,
        ok=result.ok,
        stdout=result.stdout[-60000:],
        stderr=result.stderr[-30000:],
        duration_ms=result.duration_ms,
        timed_out=result.timed_out,
        error=result.error,
        figures=[
            SandboxFigure(name=f.name, path=f.path, size_bytes=f.size_bytes, data_url=f.data_url)
            for f in result.figures
        ],
        synthesis_note=synthesis_note,
    )


@router.post("/agent/query", response_model=QueryResponse)
def agent_query(req: QueryRequest) -> QueryResponse:
    """Interrogazione delle note atomiche via collegamenti [[...]] (Skill §6)."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Domanda vuota")
    vault = _vault()
    res = run_query(vault, req.question, llm=get_llm_client(), top_k=req.top_k)
    return QueryResponse(provider=res.provider, answer_markdown=res.answer_markdown,
                         citations=res.citations)


# ---------------------------------------------------------------------------
# Endpoint di supporto per la UI
# ---------------------------------------------------------------------------

@router.get("/health")
def health() -> dict:
    s = _state()
    return {
        "ok": True,
        "app": settings.app_name,
        "version": "0.1.0",
        "vault_open": s.vault is not None,
        "vault_root": str(s.vault.root) if s.vault else None,
        "llm": _llm_dict(),
        "sandbox_timeout_seconds": settings.sandbox_timeout_seconds,
    }


@router.get("/llm/status")
def llm_status_endpoint() -> dict:
    return _llm_dict()


@router.get("/vault/tree")
def vault_tree() -> dict:
    """Albero del vault per la tree-view della colonna sinistra."""
    vault = _vault()

    def walk(p: Path) -> dict:
        rel = vault.rel(p)
        entry: dict = {"name": p.name, "path": rel, "type": "dir" if p.is_dir() else "file"}
        if p.is_dir():
            children = []
            for child in sorted(p.iterdir(), key=lambda c: (c.is_file(), c.name.casefold())):
                if child.name.startswith(".") and child == p:
                    continue
                children.append(walk(child))
            entry["children"] = children
        else:
            entry["size"] = p.stat().st_size
        return entry

    return walk(vault.root)


@router.get("/vault/info")
def vault_info() -> dict:
    vault = _vault()
    s = _state()
    graph = build_graph(vault, build_registry(vault))
    altered = vault.verify_sources()
    return {
        "root": str(vault.root),
        "opened_at": s.opened_at,
        "nodes": graph["node_count"],
        "edges": graph["edge_count"],
        "integrity": {"ok": not altered, "altered": altered},
    }


@router.get("/notes")
def list_notes() -> list[dict]:
    vault = _vault()
    out = []
    reg = build_registry(vault)
    for node in sorted(reg.nodes.values(), key=lambda n: n.id):
        if node.type == "source":
            continue
        out.append({
            "id": node.id,
            "title": node.title,
            "type": node.type,
            "tags": node.tags,
            "aliases": node.aliases,
            "abstract": node.abstract,
        })
    return out


@router.get("/notes/{relpath:path}")
def read_note(relpath: str) -> dict:
    vault = _vault()
    p = _resolve_vault_path(relpath)
    if not p.is_file() or p.suffix != ".md" or not str(relpath).startswith("wiki/"):
        raise HTTPException(status_code=404, detail="Nota non trovata")
    raw = p.read_text(encoding="utf-8")
    try:
        note, body = parse_frontmatter(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"path": relpath, "frontmatter": note.model_dump(), "body": body, "raw": raw}


@router.put("/notes/{relpath:path}")
def save_note(relpath: str, req: NoteSaveRequest) -> dict:
    vault = _vault()
    p = _resolve_vault_path(relpath)
    if not str(relpath).startswith("wiki/") or p.suffix != ".md":
        raise HTTPException(status_code=400, detail="Scrivibile solo in wiki/**/*.md")
    try:
        note, body = parse_frontmatter(req.content)
    except (ValueError, Exception) as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Frontmatter non valido: {exc}")
    if note.type not in NOTE_TYPES:
        raise HTTPException(status_code=422, detail="type non valido")
    missing = [s for s in REQUIRED_SECTIONS
               if not re.search(rf"^##\s+{re.escape(s)}\s*$", body, re.MULTILINE)]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_note(note, body), encoding="utf-8")
    write_indexes(vault)
    return {"path": relpath, "saved": True, "missing_sections": missing,
            "note": note.model_dump()}


@router.delete("/notes/{relpath:path}")
def delete_note(relpath: str) -> dict:
    vault = _vault()
    p = _resolve_vault_path(relpath)
    if not str(relpath).startswith("wiki/") or not p.is_file():
        raise HTTPException(status_code=400, detail="Si possono eliminare solo note wiki esistenti")
    p.unlink()
    write_indexes(vault)
    return {"path": relpath, "deleted": True}


@router.get("/index")
def index_md() -> dict:
    vault = _vault()
    content = vault.index_md.read_text(encoding="utf-8") if vault.index_md.exists() else ""
    return {"path": "_index/INDEX.md", "content": content}


@router.post("/index/rebuild")
def index_rebuild() -> dict:
    vault = _vault()
    graph = write_indexes(vault)
    return {"rebuilt": True, "nodes": graph["node_count"], "edges": graph["edge_count"]}


@router.get("/lint/report")
def lint_report() -> dict:
    vault = _vault()
    return {"path": "_index/lint_report.md", "content": load_lint_report(vault)}


@router.get("/files/{relpath:path}")
def vault_file(relpath: str) -> FileResponse:
    """Servizio file del vault (immagini generate, sorgenti per anteprima)."""
    p = _resolve_vault_path(relpath)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="File non trovato")
    return FileResponse(p)


# ---------------------------------------------------------------------------
# Pipeline C passo 5 — nota di sintesi post-esecuzione (deterministica)
# ---------------------------------------------------------------------------

def _validate_dataset_path(rel: str) -> str:
    vault = _vault()
    cleaned = rel.replace("\\", "/").lstrip("/")
    if not cleaned.startswith("datasets/"):
        raise HTTPException(status_code=400,
                            detail="Il dataset deve essere in sources/datasets/ (es. 'datasets/vendite.csv')")
    p = (vault.sources / cleaned).resolve()
    if not p.is_file() or vault.sources.resolve() not in p.parents:
        raise HTTPException(status_code=404, detail=f"Dataset non trovato: {cleaned}")
    return cleaned


def _build_synthesis_note(vault: Vault, req: SandboxRunRequest, result) -> str:
    """Compila wiki/synthesis/analisi_{task}.md con evidenze dell'esecuzione.

    Deterministica: riportiamo output, figure e metriche estratte da stdout
    (pattern `**nome**: valore` e `key=value`); con un LLM configurato questo
    stesso payload verrebbe arricchito dalla spiegazione teorica del modello.
    """
    from datetime import date

    task = (req.task_name or "analisi").strip()
    slug = slugify(task)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    rel = f"wiki/synthesis/analisi-{slug}-{stamp}.md"
    target = vault.root / rel
    i = 2
    while target.exists():
        target = vault.root / f"wiki/synthesis/analisi-{slug}-{stamp}_{i}.md"
        i += 1

    stdout = result.stdout
    metrics: list[str] = []
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_ ]{2,40}?)\s*[:=]\s*(-?[0-9][0-9.,]*)", stdout):
        key, val = m.group(1).strip(), m.group(2)
        try:
            float(val.replace(",", "."))
        except ValueError:
            continue
        if len(metrics) < 15:
            metrics.append(f"- **{key}**: {val}")

    figs = "\n".join(f"![[{f.path}]]" for f in result.figures) or "- (nessuna figura generata)"
    provenance: list[str] = []
    if req.dataset:
        provenance.append(f"[[sources/{req.dataset}]]")
    provenance.append(f"[[scripts/{result.script_path.split('/', 1)[1]}]]"
                      if "/" in result.script_path else f"[[{result.script_path}]]")

    note = WikiNote(
        title=f"Analisi: {task}",
        type="synthesis",
        created=date.today().isoformat(),
        updated=date.today().isoformat(),
        sources=provenance,
        tags=["dati/analisi"],
    )
    body = (
        f"# Analisi: {task}\n\n"
        f"## Sintesi Esecutiva\n\n"
        f"Esecuzione sandbox `{result.script_path}` completata in {result.duration_ms} ms "
        f"(exit {result.exit_code})"
        + (f" sul dataset `[[sources/{req.dataset}]]`" if req.dataset else "")
        + ".\n\n"
        f"## Formalizzazione & Dettagli\n\n"
        f"**Metodo**: esecuzione di codice Python nel kernel isolato "
        f"(`sandbox`, timeout {settings.sandbox_timeout_seconds}s). La spiegazione "
        f"teorica del test statistico è compilata in modo deterministico; con un "
        f"provider LLM configurato questa sezione è arricchita automaticamente.\n\n"
        f"**Risultati numerici estratti dall'output**\n\n"
        + ("\n".join(metrics) if metrics else "- (nessuna metrica numerica nell'output)")
        + "\n\n"
        f"**Output completo (tracciato)**\n\n```\n{stdout[-4000:]}\n```\n\n"
        f"**Figure generate**\n\n{figs}\n\n"
        f"## Relazioni nel Grafo\n\n"
        + "\n".join(f"- {p}" for p in provenance)
        + "\n\n"
        f"## Discrepanze & Limiti\n\n"
        f"- Esecuzione in sandbox: stato della sessione non persistente tra esecuzioni.\n"
        f"- Sintesi deterministica offline (nessun modello AI attivo).\n"
    )
    target.write_text(render_note(note, body), encoding="utf-8")
    write_indexes(vault)
    return target.name
