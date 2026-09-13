"""Ricerca deterministica full-text sull'indice compilato (no AI).

Score TF su titoli/alias (peso alto), abstract e corpo; espansione a un
salto lungo gli archi del grafo per il contesto. Il servizio di query
usa questo motore in modalità offline; con un provider LLM configurato,
lo stesso contesto viene passato al modello (prompt in compiler/prompts.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..compiler.links import LinkRegistry, strip_links
from ..core.vault import Vault

STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "di", "del", "della", "de", "a", "al",
    "alla", "in", "nel", "nella", "per", "che", "e", "o", "un", "una", "con",
    "su", "tra", "dal", "dai", "dalla", "the", "of", "and", "to", "in", "for",
    "is", "are", "with", "how", "what", "why", "come", "cosa", "perche", "che",
}


@dataclass
class ScoredNote:
    id: str
    title: str
    score: float
    excerpt: str


def _tokens(text: str) -> list[str]:
    toks = re.findall(r"[a-zà-ù0-9_]{2,}", text.casefold())
    return [t for t in toks if t not in STOPWORDS]


def retrieve(vault: Vault, registry: LinkRegistry, question: str,
             top_k: int = 5, include_neighbors: bool = True) -> list[ScoredNote]:
    q_tokens = _tokens(question)
    if not q_tokens:
        return []
    q_set = set(q_tokens)
    qf = {t: q_tokens.count(t) for t in q_set}

    scores: dict[str, float] = {}
    for node in registry.nodes.values():
        if node.type == "source":
            continue
        title_tokens = _tokens(node.title) + [_tokens(a) for a in node.aliases]
        flat_title: list[str] = []
        for chunk in title_tokens:
            flat_title.extend(chunk)
        score = 0.0
        for t in q_set:
            if t in flat_title:
                score += 5.0 * qf[t]
        abs_tokens = set(_tokens(node.abstract))
        for t in q_set:
            if t in abs_tokens:
                score += 2.0 * qf[t]
        body_tokens = set(_tokens(strip_links(node.body)))
        for t in q_set:
            if t in body_tokens:
                score += 1.0 * qf[t]
        if score > 0:
            scores[node.id] = score

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[: max(top_k, 1)]
    chosen_ids = {nid for nid, _ in ranked}

    if include_neighbors:
        adjacency: dict[str, set[str]] = {}
        for node in registry.nodes.values():
            for raw in re.findall(r"\[\[([^\[\]|\n]+?)(?:\|([^\[\]\n]+?))?\]\]", node.body):
                target = registry.resolve(raw[0]).target
                if target:
                    adjacency.setdefault(node.id, set()).add(target)
                    adjacency.setdefault(target, set()).add(node.id)
        for nid, base in ranked:
            for nb in adjacency.get(nid, ()):  # type: ignore[arg-type]
                if nb in chosen_ids or nb not in registry.nodes:
                    continue
                nb_node = registry.nodes[nb]
                if nb_node.type == "source":
                    continue
                # il vicino entra solo se condivide almeno un token con la query
                nb_tokens = set(_tokens(nb_node.title)) | set(_tokens(nb_node.abstract))
                if q_set & nb_tokens:
                    chosen_ids.add(nb)

    out: list[ScoredNote] = []
    for nid in chosen_ids:
        node = registry.nodes.get(nid)
        if not node:
            continue
        out.append(ScoredNote(
            id=nid,
            title=node.title,
            score=scores.get(nid, 0.5),
            excerpt=(node.abstract or "")[:240],
        ))
    out.sort(key=lambda s: (-s.score, s.id))
    return out[: max(top_k * 2, top_k)]


def format_context(notes: list[ScoredNote]) -> str:
    if not notes:
        return "(nessuna nota rilevante nell'indice)"
    blocks = []
    for n in notes:
        blocks.append(f"### [[{n.id}]] — {n.title}\n{n.excerpt}")
    return "\n\n".join(blocks)


def deterministic_answer(question: str, notes: list[ScoredNote]) -> str:
    """Composizione offline della risposta: evidenze tracciabili, zero allucinazioni."""
    if not notes:
        return (
            "Nessuna nota dell'indice corrisponde alla domanda. "
            "In modalità offline la risposta è derivata SOLO dalla conoscenza "
            "compilata presente nel vault."
        )
    lines = [
        f"Risposta deterministica (nessun modello AI attivo) a: *{question}*",
        "",
        "Evidenze dalla conoscenza compilata:",
        "",
    ]
    for n in notes:
        lines.append(f"- **[[{n.id}]]** — {n.title} — {n.excerpt}")
    lines.append("")
    lines.append(
        "_Per sintesi semantica complete: configurare un provider nel layer LLM "
        "(`LLM_PROVIDER=openai|anthropic|ollama`); il contratto di risposta resterà identico._"
    )
    return "\n".join(lines)
