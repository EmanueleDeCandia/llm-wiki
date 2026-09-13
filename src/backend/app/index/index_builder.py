"""Generatore/aggiornatore di `_index/INDEX.md` e `_index/graph.json` (Skill §2, §4-A.4).

Il grafo G = (V, E): V = note Markdown di `wiki/` + file di `sources/`;
E = archi da wikilink nel corpo, dalle relations del frontmatter e dalla
provenienza delle fonti. Ogni arco è orientato ma il rendering è
bidirezionale (backlink calcolati, come in Obsidian).
"""
from __future__ import annotations

import json

from ..compiler.links import GraphNode, LinkRegistry, extract_link_targets
from ..core.vault import Vault
from ..schemas.wiki import utcnow_iso

EDGE_KINDS = ("prerequisite", "related", "conflict", "source")


def build_registry(vault: Vault) -> LinkRegistry:
    reg = LinkRegistry()
    wiki = vault.wiki
    for sub in ("concepts", "entities", "synthesis"):
        for p in sorted((wiki / sub).glob("*.md")):
            reg.add_note(vault.rel(p), vault.root)
    for p in sorted(vault.sources.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        if not vault._is_generated_output(p):
            reg.add_source(vault.rel(p))
    # Artefatti gestiti dall'app (figure sandbox, script generati): sono nodi
    # del grafo per la tracciabilità della provenienza delle sintesi.
    for p in sorted(vault.generated_images.rglob("*")):
        if p.is_file() and not p.name.startswith(".") and p.name != "llw_manifest.json":
            reg.add_source(vault.rel(p))
    for p in sorted(vault.generated_scripts.rglob("*.py")):
        if p.is_file():
            reg.add_source(vault.rel(p))
    return reg


def _collect_edges(vault: Vault, reg: LinkRegistry) -> list[dict]:
    edges: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add(src: str, dst: str, kind: str) -> None:
        if src == dst:
            return
        key = (src, dst, kind)
        if key in seen:
            return
        seen.add(key)
        edges.append({"source": src, "target": dst, "kind": kind})

    from ..schemas.wiki import parse_frontmatter

    for node in reg.nodes.values():
        if node.type == "source":
            continue
        try:
            note, _body = parse_frontmatter((vault.root / node.id).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for s in note.sources:
            target = reg.resolve(s[2:-2] if s.startswith("[[") and s.endswith("]]") else s)
            if target.target:
                add(node.id, target.target, "source")
        for p in note.relations.prerequisites:
            t = reg.resolve(_bare(p))
            if t.target:
                add(node.id, t.target, "prerequisite")
        for p in note.relations.related:
            t = reg.resolve(_bare(p))
            if t.target:
                add(node.id, t.target, "related")
        for p in note.relations.conflicts_with:
            t = reg.resolve(_bare(p))
            if t.target:
                add(node.id, t.target, "conflict")
        for raw in extract_link_targets(node.body):
            t = reg.resolve(raw)
            if t.target and t.target != node.id:
                kind = "source" if t.target.startswith("sources/") else "related"
                add(node.id, t.target, kind)
    return edges


def _bare(link: str) -> str:
    link = link.strip()
    if link.startswith("[[") and link.endswith("]]"):
        link = link[2:-2]
    return link.split("|", 1)[0].strip()


def build_graph(vault: Vault, reg: LinkRegistry | None = None) -> dict:
    reg = reg or build_registry(vault)
    edges = _collect_edges(vault, reg)
    nodes = [
        {
            "id": n.id,
            "title": n.title,
            "type": n.type,
            "tags": n.tags,
            "aliases": n.aliases,
            "abstract": n.abstract,
        }
        for n in sorted(reg.nodes.values(), key=lambda n: n.id)
    ]
    return {
        "version": 1,
        "generated_at": utcnow_iso(),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def render_index_markdown(existing: dict[str, list[str]]) -> str:
    """Indice testuale (per i prompt LLM e il debug): id -> [title, aliases]."""
    if not existing:
        return ""
    lines = []
    for node_id, names in sorted(existing.items()):
        title = names[0] if names else node_id
        lines.append(f"- [[{node_id}]] — {title}")
    return "\n".join(lines)


def build_index_md(vault: Vault, reg: LinkRegistry) -> str:
    order = {"concept": 0, "entity": 1, "dataset": 2, "synthesis": 3}
    by_type: dict[str, list[GraphNode]] = {"concept": [], "entity": [], "dataset": [], "synthesis": []}
    for n in reg.nodes.values():
        if n.type in by_type:
            by_type[n.type].append(n)
    lines = [
        "# INDEX — Master Index della Conoscenza Compilata",
        "",
        f"> Generato automaticamente dal motore LLM Wiki — {utcnow_iso()}.",
        "> Formato: `- [[path]] — abstract su riga singola | tag: a, b`",
        "",
    ]
    labels = {"concept": "concetti", "entity": "entità", "dataset": "dataset", "synthesis": "sintesi"}
    for key in ("concept", "entity", "dataset", "synthesis"):
        nodes = sorted(by_type[key], key=lambda n: n.title.casefold())
        lines.append(f"## {labels[key]} ({len(nodes)})")
        lines.append("")
        if not nodes:
            lines.append("_(vuoto)_")
        for n in nodes:
            tag_txt = ", ".join(n.tags) if n.tags else "—"
            lines.append(f"- [[{n.id}]] — {n.abstract or '(nessun abstract)'} | tag: {tag_txt}")
        lines.append("")
    sources = sorted((n for n in reg.nodes.values() if n.type == "source"), key=lambda n: n.id)
    lines.append(f"## sorgenti ({len(sources)})")
    lines.append("")
    for n in sources:
        lines.append(f"- [[{n.id}]] — sorgente immutabile")
    lines.append("")
    return "\n".join(lines)


def write_indexes(vault: Vault) -> dict:
    """Rigenera INDEX.md + graph.json e restituisce il grafo."""
    reg = build_registry(vault)
    graph = build_graph(vault, reg)
    vault.index_md.write_text(build_index_md(vault, reg), encoding="utf-8")
    vault.graph_json.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph
