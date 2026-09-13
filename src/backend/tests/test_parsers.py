"""Test dei parser multimodali (Step 1 della Skill: core ingestion)."""
from __future__ import annotations

from pathlib import Path

from app.parsers.registry import ParserRegistry
from app.parsers.tables import table_to_markdown

from .conftest import SAMPLE_PAPER, build_simple_docx, build_simple_pdf, build_table_pdf


def test_text_parser(tmp_path: Path) -> None:
    p = tmp_path / "paper.txt"
    p.write_text(SAMPLE_PAPER, encoding="utf-8")
    reg = ParserRegistry()
    parsed = reg.parse_document(p, "sources/papers/paper.txt")
    assert parsed.title == "Attention-Based Sequence Models"
    assert "Attention Mechanism" in parsed.headings
    assert "$a_{ij}" in parsed.markdown  # LaTeX conservato intatto
    assert parsed.word_count > 50


def test_pdf_parser(tmp_path: Path) -> None:
    p = tmp_path / "paper.pdf"
    build_simple_pdf(
        ["The Transformer Model", "Attention is all you need.", "Scaling laws dominate."],
        p,
    )
    reg = ParserRegistry()
    parsed = reg.parse_document(p, "sources/papers/paper.pdf")
    assert "Transformer Model" in parsed.markdown
    assert "Attention is all you need" in parsed.markdown
    assert parsed.parser_name.startswith("pdf:")


def test_pdf_table_extraction_built_in(tmp_path: Path) -> None:
    """Il built-in pypdf+tables deve trasformare le regioni allineate in tabelle
    Markdown (e preservare il testo libero circostante)."""
    p = tmp_path / "report.pdf"
    build_table_pdf(
        ["Quarterly report for the fiscal year.", "The figures below are unaudited."],
        [
            ["Month", "Units", "Revenue"],
            ["Jan", "120", "1450.50"],
            ["Feb", "95", "1180.25"],
            ["Mar", "210", "2675.00"],
        ],
        p,
    )
    reg = ParserRegistry()
    # vincolato al built-in per il test (indipendente da docling/eventuali installazioni)
    reg.pdf.engine = "pypdf"
    parsed = reg.parse_document(p, "sources/papers/report.pdf")

    assert "| Month | Units | Revenue |" in parsed.markdown
    assert "| Jan | 120 | 1450.50 |" in parsed.markdown
    assert "| Mar | 210 | 2675.00 |" in parsed.markdown
    # testo libero preservato nel flusso
    assert "Quarterly report for the fiscal year." in parsed.markdown
    # ParsedTable strutturato
    assert len(parsed.tables) == 1
    t = parsed.tables[0]
    assert t.header == ["Month", "Units", "Revenue"]
    assert len(t.rows) == 3
    assert t.rows[0] == ["Jan", "120", "1450.50"]
    # allineamento numerico delle colonne
    assert "---:" in table_to_markdown(t)
    # il parser dichiara il proprio motore
    assert parsed.parser_name == "pdf:pypdf+tables"


def test_pdf_table_ingested_into_note(tmp_path: Path, vault_root: Path) -> None:
    """E2E: PDF con tabella → nota-entità che contiene la tabella Markdown."""
    from app.core.vault import Vault
    from app.index.index_builder import write_indexes
    from app.pipeline import ingest_file
    from app.schemas.wiki import parse_frontmatter

    vault = Vault(root=vault_root, template_root=vault_root)
    vault.ensure_topology()
    write_indexes(vault)
    vault.snapshot_sources()

    p = vault.root / "sources" / "papers" / "report.pdf"
    build_table_pdf(
        ["Sales overview."],
        [["Month", "Units", "Revenue"], ["Jan", "120", "1450.50"], ["Feb", "95", "1180.25"]],
        p,
    )
    res = ingest_file(vault, p, "papers")
    assert res.sources_integrity_ok
    doc_note = [n for n in res.notes_created if n.startswith("wiki/entities/")][0]
    content = (vault.root / doc_note).read_text(encoding="utf-8")
    note, body = parse_frontmatter(content)
    assert note.type == "entity"
    assert "| Month | Units | Revenue |" in body
    assert "| Jan | 120 | 1450.50 |" in body


def test_docx_parser(tmp_path: Path) -> None:
    p = tmp_path / "notes.docx"
    build_simple_docx(p)
    reg = ParserRegistry()
    parsed = reg.parse_document(p, "sources/papers/notes.docx")
    assert parsed.title == "Vector Databases"
    assert "## Indexing" in parsed.markdown
    assert "embeddings" in parsed.markdown


def test_image_parser(sample_png: Path) -> None:
    reg = ParserRegistry()
    meta = reg.parse_image(sample_png, "sources/images/diagram.png")
    assert meta.width == 320
    assert meta.height == 200
    assert meta.format == "PNG"
    assert meta.size_bytes > 0


def test_dataset_profile_csv(sample_csv: Path) -> None:
    reg = ParserRegistry()
    prof = reg.parse_dataset(sample_csv, "sources/datasets/sales.csv")
    assert prof.error is None
    assert prof.rows == 40
    assert set(prof.dtypes) == {"revenue", "units", "region"}
    assert prof.columns[0].stats["mean"] is not None
    # correlazione revenue-units > 0 (unità x prezzo ~ lineare)
    assert "revenue" in prof.correlations
    assert prof.correlations["revenue"]["units"] > 0.5
    assert len(prof.sample_records) == 5


def test_dataset_profile_sqlite(sample_sqlite: Path) -> None:
    reg = ParserRegistry()
    prof = reg.parse_dataset(sample_sqlite, "sources/datasets/users.sqlite")
    assert prof.error is None
    assert prof.rows == 24
    assert "age" in prof.dtypes and "score" in prof.dtypes
