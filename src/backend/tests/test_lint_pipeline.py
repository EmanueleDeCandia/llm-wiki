"""Test della Pipeline B — Knowledge Linting (Step 5 della Skill)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from app.core.vault import Vault
from app.index.index_builder import write_indexes
from app.lint.lint_engine import run_lint, write_lint_report
from app.schemas.wiki import NoteRelations, WikiNote, render_note

TODAY = date.today().isoformat()


def _note(title: str, body: str, sources: list[str],
          relations: NoteRelations | None = None) -> str:
    n = WikiNote(
        title=title, type="concept", created=TODAY, updated=TODAY,
        sources=sources, relations=relations or NoteRelations(),
    )
    return render_note(n, body)


def _body(title: str, rel_links: str = "", extra: str = "") -> str:
    return (
        f"# {title}\n\n"
        "## Sintesi Esecutiva\n\nFrase di sintesi.\n\n"
        "## Formalizzazione & Dettagli\n\nDettaglio.\n\n"
        f"## Relazioni nel Grafo\n\n{rel_links}\n\n"
        "## Discrepanze & Limiti\n\nNessuno.\n"
        f"{extra}"
    )


def _vault_with(root: Path, notes: dict[str, str]) -> Vault:
    vault = Vault(root=root, template_root=None)
    vault.ensure_topology()
    for rel, content in notes.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    # Crea i file sorgenti referenziati (senza di essi ogni provenienza
    # diventerebbe un link orfano).
    import re as _re

    for content in notes.values():
        for src in _re.findall(r"\[\[(sources/[^\]]+)\]\]", content):
            sp = root / src
            sp.parent.mkdir(parents=True, exist_ok=True)
            if not sp.exists():
                sp.write_bytes(b"%PDF-1.4 dummy\n")
    write_indexes(vault)
    return vault


def test_orphan_isolated_and_components(vault_root: Path) -> None:
    notes = {
        # A punta a B (esistente) e a [[NonEsistente]] (orfano)
        "wiki/concepts/a.md": _note(
            "Alpha",
            _body("Alpha", "- Correlate: [[Beta]], [[NonEsistente]]"),
            ["[[sources/papers/x.pdf]]"],
        ),
        # B collegata ad A
        "wiki/concepts/b.md": _note(
            "Beta",
            _body("Beta", "- Correlate: [[Alpha]]"),
            ["[[sources/papers/x.pdf]]"],
        ),
        # C isolata (deg=0)
        "wiki/concepts/c.md": _note(
            "Gamma",
            _body("Gamma"),
            ["[[sources/papers/x.pdf]]"],
        ),
    }
    vault = _vault_with(vault_root, notes)
    res = run_lint(vault)

    orphans = [o["target"] for o in res.orphan_links]
    assert "NonEsistente" in orphans, "link orfano non rilevato"

    assert "wiki/concepts/c.md" in res.isolated_nodes, "nodo isolato non rilevato"
    assert len(res.components) >= 2, "cluster disconnessi non rilevati"


def test_semantic_conflict_on_diverging_metrics(vault_root: Path) -> None:
    notes = {
        "wiki/concepts/m1.md": _note(
            "Modello Uno",
            _body("Modello Uno", "- Correlate: [[Modello Due]]",
                  extra="\n**Precisione**: 0.92\n"),
            ["[[sources/papers/x.pdf]]"],
        ),
        "wiki/concepts/m2.md": _note(
            "Modello Due",
            _body("Modello Due", "- Correlate: [[Modello Uno]]",
                  extra="\n**Precisione**: 0.71\n"),
            ["[[sources/papers/y.pdf]]"],
        ),
    }
    vault = _vault_with(vault_root, notes)
    res = run_lint(vault)
    assert res.conflicts, "conflitto metriche non rilevato"
    c = res.conflicts[0]
    assert c["metric"] == "Precisione"
    assert {c["value_a"], c["value_b"]} == {0.92, 0.71}


def test_lint_report_written(vault_root: Path) -> None:
    notes = {
        "wiki/concepts/a.md": _note(
            "Alpha",
            _body("Alpha", "- Correlate: [[Orfano Totale]]"),
            ["[[sources/papers/x.pdf]]"],
        ),
    }
    vault = _vault_with(vault_root, notes)
    write_lint_report(vault)
    report = vault.lint_report.read_text(encoding="utf-8")
    assert "Link orfani" in report
    assert "Orfano Totale" in report


def test_clean_vault_reports_clean(vault_root: Path) -> None:
    notes = {
        "wiki/concepts/a.md": _note(
            "Alpha",
            _body("Alpha", "- Correlate: [[Beta]]"),
            ["[[sources/papers/x.pdf]]"],
        ),
        "wiki/concepts/b.md": _note(
            "Beta",
            _body("Beta", "- Correlate: [[Alpha]]"),
            ["[[sources/papers/x.pdf]]"],
        ),
    }
    vault = _vault_with(vault_root, notes)
    res = run_lint(vault)
    assert res.orphan_links == []
    assert res.conflicts == []
    assert res.clean
