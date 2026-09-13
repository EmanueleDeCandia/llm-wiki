"""Test della Pipeline A — IngestAndCompile (Step 2 della Skill)."""
from __future__ import annotations

import json
from pathlib import Path

from app.core.vault import Vault, sha256_file
from app.index.index_builder import build_registry, write_indexes
from app.pipeline import ingest_file
from app.schemas.wiki import REQUIRED_SECTIONS, parse_frontmatter

from .conftest import SAMPLE_PAPER, SECOND_DOC


def _open_vault(root: Path) -> Vault:
    vault = Vault(root=root, template_root=root)
    vault.ensure_topology()
    write_indexes(vault)
    vault.snapshot_sources()
    return vault


def _ingest_text(vault: Vault, name: str, content: str) -> str:
    p = vault.root / "sources" / "papers" / name
    p.write_text(content, encoding="utf-8")
    res = ingest_file(vault, p, "papers")
    assert res.sources_integrity_ok, res.sources_altered
    return name


def test_ingest_creates_atomic_notes_with_contract(vault_root: Path) -> None:
    vault = _open_vault(vault_root)
    _ingest_text(vault, "attention.txt", SAMPLE_PAPER)

    wiki = vault.wiki
    concept_files = list((wiki / "concepts").glob("*.md"))
    entity_files = list((wiki / "entities").glob("*.md"))
    assert concept_files, "devono esistere note atomiche in wiki/concepts/"
    assert entity_files, "deve esistere la nota-entità del documento"

    for f in concept_files + entity_files:
        note, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        # Frontmatter conforme al contratto
        assert note.title
        assert note.type in ("concept", "entity", "dataset", "synthesis")
        assert note.sources, "provenienza obbligatoria (§1.3)"
        assert note.sources[0].startswith("[[sources/papers/attention.txt]]")
        # Struttura del corpo (§3.2)
        assert body.startswith(f"# {note.title}")
        for section in REQUIRED_SECTIONS:
            assert f"## {section}" in body, f"manca la sezione '{section}' in {f.name}"


def test_ingest_updates_index_and_graph(vault_root: Path) -> None:
    vault = _open_vault(vault_root)
    _ingest_text(vault, "attention.txt", SAMPLE_PAPER)

    index = vault.index_md.read_text(encoding="utf-8")
    assert "wiki/concepts/" in index
    assert "[[sources/papers/attention.txt]]" in index

    graph = json.loads(vault.graph_json.read_text(encoding="utf-8"))
    ids = {n["id"] for n in graph["nodes"]}
    assert "sources/papers/attention.txt" in ids
    assert any(i.startswith("wiki/concepts/") for i in ids)
    kinds = {e["kind"] for e in graph["edges"]}
    assert "source" in kinds  # arco di provenienza


def test_sources_immutability(vault_root: Path) -> None:
    """Test di conformità Ingest: assenza di modifiche nel file sorgente (§1.2)."""
    vault = _open_vault(vault_root)
    p = vault.root / "sources" / "papers" / "attention.txt"
    p.write_text(SAMPLE_PAPER, encoding="utf-8")
    before = sha256_file(p)
    ingest_file(vault, p, "papers")
    after = sha256_file(p)
    assert before == after
    assert vault.verify_sources() == []


def test_second_document_links_existing_concepts(vault_root: Path) -> None:
    vault = _open_vault(vault_root)
    _ingest_text(vault, "attention.txt", SAMPLE_PAPER)
    reg = build_registry(vault)
    existing_titles = {n.title.casefold() for n in reg.nodes.values() if n.type == "concept"}
    assert "attention mechanism" in existing_titles

    _ingest_text(vault, "gd.txt", SECOND_DOC)
    # La nota "Stochastic Gradient Descent" del secondo documento deve
    # collegarsi bidirezionalmente a "Attention Mechanism" (presente nel testo).
    sgd = list((vault.wiki / "concepts").glob("stochastic-gradient-descent.md"))
    assert sgd, "nota attesa: stochastic-gradient-descent.md"
    note, body = parse_frontmatter(sgd[0].read_text(encoding="utf-8"))
    related_flat = " ".join(note.relations.related + note.relations.prerequisites)
    assert "attention mechanism" in related_flat.casefold()
    assert "[[Attention Mechanism]]" in body  # wikilink esplicito nel corpo


def test_ingest_dataset_creates_metadata_card(vault_root: Path, sample_csv: Path) -> None:
    vault = _open_vault(vault_root)
    dst = vault.root / "sources" / "datasets" / "sales.csv"
    dst.write_bytes(sample_csv.read_bytes())
    res = ingest_file(vault, dst, "datasets")
    assert res.notes_created, res.messages
    card_path = vault.root / res.notes_created[0]
    card = card_path.read_text(encoding="utf-8")
    note, body = parse_frontmatter(card)
    assert note.type == "dataset"
    assert "40 righe" in body or "40" in body
    assert "| revenue |" in body  # schema con statistiche
    # Invariante §1.4: la card NON contiene l'intero dataset (solo 5 righe)
    body_lines = [ln for ln in body.splitlines() if ln.startswith("|")]
    assert len(body_lines) < 30


def test_ingest_idempotent(vault_root: Path) -> None:
    vault = _open_vault(vault_root)
    _ingest_text(vault, "attention.txt", SAMPLE_PAPER)
    count_before = len(list(vault.wiki.rglob("*.md")))
    # Re-ingest dello stesso contenuto con nome diverso: le note esistono già
    res = ingest_file(vault, vault.root / "sources" / "papers" / "attention.txt", "papers")
    assert res.sources_integrity_ok
    count_after = len(list(vault.wiki.rglob("*.md")))
    assert count_after == count_before  # nessuna sovrascrittura né duplicazione


def test_ingest_image(vault_root: Path, sample_png: Path) -> None:
    vault = _open_vault(vault_root)
    dst = vault.root / "sources" / "images" / "diagram.png"
    dst.write_bytes(sample_png.read_bytes())
    res = ingest_file(vault, dst, "images")
    assert res.notes_created
    card = (vault.root / res.notes_created[0]).read_text(encoding="utf-8")
    note, _ = parse_frontmatter(card)
    assert note.type == "entity"
    assert "320" in card and "200" in card
