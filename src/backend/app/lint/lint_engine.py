"""Pipeline B — Knowledge Linting (Skill §4-B).

Costruisce il grafo orientato G = (V, E) e rileva:
* link orfani:    ∃ e = (u, v) ∈ E tale che v ∉ V
* nodi isolati:   deg(v) = 0
* cluster disconnessi: componenti debolmente connesse
* conflitti semantici: (euristica deterministica sostituibile con LLM)
  - dichiarazioni `conflicts_with` nel frontmatter
  - metriche `**nome**: valore` con valori divergenti tra note collegate
* conformità strutturale: blocchi obbligatori del corpo (§3.2) e provenienza (§1.3)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..compiler.links import LinkRegistry, extract_link_targets
from ..core.vault import Vault
from ..schemas.wiki import REQUIRED_SECTIONS, parse_frontmatter, utcnow_iso

_METRIC_RE = re.compile(r"^\s*[-*]?\s*\*\*([^*:]+)\*\*\s*:\s*([0-9][0-9.,]*)", re.MULTILINE)
_TOL = 1e-9


@dataclass
class LintResult:
    node_count: int = 0
    edge_count: int = 0
    orphan_links: list[dict] = field(default_factory=list)
    isolated_nodes: list[str] = field(default_factory=list)
    components: list[list[str]] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    structural_issues: list[dict] = field(default_factory=list)
    provenance_missing: list[str] = field(default_factory=list)
    clean: bool = False

    def to_markdown(self, vault: Vault) -> str:
        L = [
            "# Lint Report — Audit Semantico della Conoscenza",
            "",
            f"> Generato il {utcnow_iso()} dalla Pipeline B (`KnowledgeLinting`).",
            f"> Nodi: **{self.node_count}** — Archi: **{self.edge_count}**",
            "",
        ]
        if self.clean:
            L.append("✅ Nessun'anomalia rilevata: grafo coerente, nessun link orfano, nessun conflitto.")
            L.append("")
        if self.orphan_links:
            L.append(f"## 🔗 Link orfani ({len(self.orphan_links)})")
            L.append("")
            L.append("Collegamenti `[[...]]` il cui bersaglio non esiste nel vault (v ∉ V).")
            L.append("")
            for o in self.orphan_links:
                L.append(f"- `{o['note']}` → `[[{o['target']}]]`")
            L.append("")
        if self.isolated_nodes:
            L.append(f"## 🏝 Nodi isolati — deg(v) = 0 ({len(self.isolated_nodes)})")
            L.append("")
            for n in self.isolated_nodes:
                L.append(f"- `{n}`")
            L.append("")
        if len(self.components) > 1:
            L.append(f"## 🧩 Cluster disconnessi ({len(self.components)})")
            L.append("")
            for i, comp in enumerate(self.components, 1):
                L.append(f"### Cluster {i} ({len(comp)} nodi)")
                for n in comp[:12]:
                    L.append(f"- `{n}`")
                if len(comp) > 12:
                    L.append(f"- … e altri {len(comp) - 12}")
                L.append("")
        if self.conflicts:
            L.append(f"## ⚠️ Conflitti semantici ({len(self.conflicts)})")
            L.append("")
            for c in self.conflicts:
                L.append(f"- `{c['a']}` vs `{c['b']}` — metrica `{c['metric']}`: "
                         f"{c['value_a']} ≠ {c['value_b']}"
                         + (f" ({c.get('detail', '')})" if c.get("detail") else ""))
            L.append("")
        if self.provenance_missing:
            L.append(f"## 📎 Provenienza mancante ({len(self.provenance_missing)})")
            L.append("")
            for n in self.provenance_missing:
                L.append(f"- `{n}` non dichiara `sources` nel frontmatter (§1.3)")
            L.append("")
        if self.structural_issues:
            L.append(f"## 📐 Conformità strutturale ({len(self.structural_issues)})")
            L.append("")
            for s in self.structural_issues:
                L.append(f"- `{s['note']}`: manca la sezione «{s['section']}» (§3.2)")
            L.append("")
        L.append("---")
        L.append("_Metodo dei conflitti: euristica deterministica su metriche numeriche condivise "
                 "tra note collegate; sostituisibile con un rilevatore LLM tramite lo stesso contratto._")
        return "\n".join(L) + "\n"


def _parse_value(s: str) -> float | None:
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def run_lint(vault: Vault, registry: LinkRegistry | None = None) -> LintResult:
    reg = registry or _build_full_registry(vault)
    result = LintResult()
    wiki_nodes = [n for n in reg.nodes.values() if n.type != "source"]
    all_ids = set(reg.nodes)
    result.node_count = len(wiki_nodes)

    # -- archi e orfani ------------------------------------------------------
    adjacency: dict[str, set[str]] = {n.id: set() for n in wiki_nodes}
    edge_count = 0
    metrics_by_node: dict[str, dict[str, float]] = {}

    all_wiki_ids = {n.id for n in wiki_nodes}
    for node in wiki_nodes:
        path = vault.root / node.id
        try:
            note, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not note.sources:
            result.provenance_missing.append(node.id)
        for section in REQUIRED_SECTIONS:
            if not re.search(rf"^##\s+{re.escape(section)}\s*$", body, re.MULTILINE):
                result.structural_issues.append({"note": node.id, "section": section})
        m = {}
        for name, val in _METRIC_RE.findall(body):
            v = _parse_value(val)
            if v is not None:
                m[name.strip()] = v
        metrics_by_node[node.id] = m

        targets: list[tuple[str, bool]] = []  # (raw, resolved)
        for raw in extract_link_targets(body):
            r = reg.resolve(raw)
            targets.append((raw, r.target is not None))
            if r.target:
                edge_count += 1
                if r.target in all_wiki_ids:
                    adjacency.setdefault(node.id, set()).add(r.target)
                    adjacency.setdefault(r.target, set()).add(node.id)
        for raw in note.sources + list(note.relations.prerequisites) + \
            list(note.relations.related) + list(note.relations.conflicts_with):
            clean = raw[2:-2] if raw.startswith("[[") and raw.endswith("]]") else raw
            clean = clean.split("|", 1)[0].strip()
            r = reg.resolve(clean)
            if r.target:
                # Gli archi verso le sorgenti contano per edge_count ma NON
                # per isolamento: una nota collegata solo alla propria fonte è
                # semanticamente isolata nel grafo della conoscenza.
                if r.target in all_wiki_ids:
                    adjacency.setdefault(node.id, set()).add(r.target)
                    adjacency.setdefault(r.target, set()).add(node.id)
            else:
                targets.append((clean, False))

        for raw, ok in targets:
            if not ok:
                result.orphan_links.append({"note": node.id, "target": raw})

    result.edge_count = edge_count

    # -- nodi isolati (solo wiki, deg=0 nel grafo completo) -------------------
    for n in wiki_nodes:
        if not adjacency.get(n.id):
            result.isolated_nodes.append(n.id)

    # -- componenti debolmente connesse ---------------------------------------
    result.components = _components(wiki_nodes, adjacency)

    # -- conflitti semantici (euristica deterministica) ------------------------
    # 1) metriche numeriche condivise con valori divergenti tra note collegate
    for i, a in enumerate(wiki_nodes):
        for b in wiki_nodes[i + 1 :]:
            connected = (a.id in adjacency.get(b.id, set())) or (b.id in adjacency.get(a.id, set()))
            if not connected:
                continue
            ma, mb = metrics_by_node.get(a.id, {}), metrics_by_node.get(b.id, {})
            for key in set(ma) & set(mb):
                if abs(ma[key] - mb[key]) > _TOL:
                    result.conflicts.append({
                        "a": a.id, "b": b.id, "metric": key,
                        "value_a": ma[key], "value_b": mb[key],
                        "detail": "valori divergenti tra note collegate",
                    })
    # 2) dichiarazioni esplicite conflicts_with nel frontmatter
    for node in wiki_nodes:
        try:
            note_a, _ = parse_frontmatter((vault.root / node.id).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for conflict in note_a.relations.conflicts_with:
            clean = conflict[2:-2] if conflict.startswith("[[") and conflict.endswith("]]") else conflict
            clean = clean.split("|", 1)[0].strip()
            r = reg.resolve(clean)
            if r.target:
                result.conflicts.append({
                    "a": node.id, "b": r.target, "metric": "—",
                    "value_a": "—", "value_b": "—",
                    "detail": "dichiarato in `conflicts_with`",
                })

    result.clean = not (
        result.orphan_links or result.isolated_nodes
        or len(result.components) > 1 or result.conflicts
        or result.structural_issues or result.provenance_missing
    )
    return result


def _build_full_registry(vault: Vault) -> LinkRegistry:
    from ..index.index_builder import build_registry

    return build_registry(vault)


def _components(wiki_nodes, adjacency: dict[str, set[str]]) -> list[list[str]]:
    seen: set[str] = set()
    comps: list[list[str]] = []
    for n in wiki_nodes:
        if n.id in seen:
            continue
        stack, comp = [n.id], []
        seen.add(n.id)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nb in adjacency.get(cur, ()):  # type: ignore[arg-type]
                if nb in {x.id for x in wiki_nodes} and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        comps.append(sorted(comp))
    comps.sort(key=lambda c: (-len(c), c[0]))
    return comps


def write_lint_report(vault: Vault, result: LintResult | None = None) -> LintResult:
    result = result or run_lint(vault)
    vault.lint_report.write_text(result.to_markdown(vault), encoding="utf-8")
    return result


def load_lint_report(vault: Vault) -> str:
    p: Path = vault.lint_report
    return p.read_text(encoding="utf-8") if p.exists() else "# Lint Report\n\n_Nessun audit eseguito._\n"
