"""Estrazione, risoluzione e costruzione dei wikilink `[[...]]` (Skill §1.3)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..schemas.wiki import WikiNote, parse_frontmatter

WIKILINK_RE = re.compile(r"\[\[([^\[\]|\n]+?)(?:\|([^\[\]\n]+?))?\]\]")


@dataclass
class GraphNode:
    id: str  # percorso relativo al vault: wiki/concepts/x.md oppure sources/papers/y.pdf
    title: str
    type: str  # concept | entity | dataset | synthesis | source
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    abstract: str = ""
    body: str = ""


@dataclass
class LinkResolution:
    raw: str
    target: Optional[str]  # node id risolto, None => link orfano
    display: str


class LinkRegistry:
    """Indice dei nodi del vault (note wiki + file sorgenti) per la
    risoluzione dei `[[wikilink]]`: per titolo, alias, slug o path."""

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self._by_title: dict[str, str] = {}

    # -- costruzione ---------------------------------------------------------
    def add_note(self, rel_path: str, root: Path) -> Optional[GraphNode]:
        path = (root / rel_path).resolve()
        try:
            note: WikiNote
            note, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — file non conformi: restano esclusi dall'indice
            return None
        node = self._from_note(rel_path, note, body)
        return node

    def add_source(self, rel_path: str) -> GraphNode:
        stem = Path(rel_path).stem.replace("_", " ").replace("-", " ").title()
        node = GraphNode(id=rel_path, title=stem, type="source")
        self._register(node)
        return node

    def _from_note(self, rel_path: str, note: WikiNote, body: str) -> GraphNode:
        node = GraphNode(
            id=rel_path,
            title=note.title,
            type=note.type,
            tags=list(note.tags),
            aliases=list(note.aliases),
            abstract=extract_abstract(body),
            body=body,
        )
        return self._register(node)

    def _register(self, node: GraphNode) -> GraphNode:
        self.nodes[node.id] = node
        self._index_name(node.title, node.id)
        self._index_name(Path(node.id).stem, node.id)
        for alias in node.aliases:
            self._index_name(alias, node.id)
        return node

    def _index_name(self, name: str, node_id: str) -> None:
        key = name.strip().casefold()
        if key and key not in self._by_title:
            self._by_title[key] = node_id

    # -- risoluzione ---------------------------------------------------------
    def resolve(self, raw: str) -> LinkResolution:
        raw = raw.strip()
        display = raw
        target: Optional[str] = None
        if raw in self.nodes:  # path esplicito (es. [[sources/papers/a.pdf]])
            target = raw
        else:
            key = raw.casefold()
            target = self._by_title.get(key)
            if target is None:  # fallback: ultimo segmento come slug
                tail = raw.rsplit("/", 1)[-1]
                target = self._by_title.get(tail.casefold())
                if target is None:
                    slug = re.sub(r"[^\w]+", "_", tail.casefold()).strip("_")
                    for nid in self.nodes:
                        if Path(nid).stem.casefold() == slug:
                            target = nid
                            break
        return LinkResolution(raw=raw, target=target, display=display)

    def node_or_create_source(self, rel_path: str, root: Path) -> GraphNode:
        if rel_path in self.nodes:
            return self.nodes[rel_path]
        if rel_path.startswith("wiki/"):
            return self.add_note(rel_path, root) or GraphNode(id=rel_path, title=Path(rel_path).stem, type="entity")
        return self.add_source(rel_path)


def extract_links(text: str) -> list[LinkResolution]:
    return [m for m in WIKILINK_RE.finditer(text)]


def extract_link_targets(text: str) -> list[str]:
    return [m.group(1).strip() for m in WIKILINK_RE.finditer(text)]


def strip_links(text: str) -> str:
    """`[[Titolo|display]]` -> `display`; `[[Titolo]]` -> `Titolo`."""
    return WIKILINK_RE.sub(lambda m: m.group(2) or m.group(1), text)


def extract_abstract(body_md: str, limit: int = 180) -> str:
    """Abstract su riga singola per _index/INDEX.md: prima frase della sezione
    Sintesi Esecutiva, altrimenti prima frase del corpo."""
    m = re.search(r"##\s+Sintesi Esecutiva\s*\n+(.+?)(?:\n##|\Z)", body_md, re.DOTALL)
    source = m.group(1) if m else body_md
    source = strip_links(source)
    source = re.sub(r"\s+", " ", source).strip()
    if len(source) > limit:
        cut = source[:limit].rsplit(" ", 1)[0]
        source = cut + "…"
    return source
