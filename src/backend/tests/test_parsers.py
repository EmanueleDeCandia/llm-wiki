"""Test dei parser multimodali (Step 1 della Skill: core ingestion)."""
from __future__ import annotations

from pathlib import Path

from app.parsers.registry import ParserRegistry

from .conftest import SAMPLE_PAPER, build_simple_docx, build_simple_pdf


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
