"""Fixture condivise: vault temporaneo, PDF/DOCX/PNG/CSV sintetici."""
from __future__ import annotations

import io
import re
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
VAULT_TEMPLATE = REPO / "vault_template"

SAMPLE_PAPER = """# Attention-Based Sequence Models

The attention mechanism allocates capacity to the most relevant parts of a sequence.
Its core weight is defined as $a_{ij} = \\frac{e^{q_i \\cdot k_j}}{\\sum_{k} e^{q_i \\cdot k_k}}$.

## Attention Mechanism

The attention mechanism computes a weighted sum of values: $z_i = \\sum_j a_{ij} v_j$.
It requires a query vector and a set of key-value pairs.
This operation is the foundation of modern sequence models.

## Training Procedure

Training uses stochastic gradient descent with learning rate $\\eta = 0.001$.
The loss is the cross-entropy between targets and predictions.
Convergence typically occurs within a few epochs on small corpora.

## Evaluation

Evaluation reports accuracy on a held-out set.
Standard metrics include precision and recall.
The dataset used in this work is the `sales` dataset.
"""

SECOND_DOC = """# Gradient Descent Notes

Gradient descent iterates $\\theta_{t+1} = \\theta_t - \\eta \\nabla L(\\theta_t)$.

## Stochastic Gradient Descent

Stochastic gradient descent is based on the attention mechanism? No: it requires
only gradients. It is a prerequisite of deep training.

## Momentum

Momentum accelerates the gradient descent updates.
"""


@pytest.fixture()
def vault_root(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    shutil.copytree(VAULT_TEMPLATE, root)
    return root


def build_simple_pdf(lines: list[str], path: Path) -> None:
    """Costruisce un PDF a una pagina con testo corretto (xref validi)."""
    esc = lambda s: s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")  # noqa: E731
    ops = []
    y = 760
    for line in lines:
        ops.append(f"BT /F1 11 Tf 56 {y} Td ({esc(line)}) Tj ET")
        y -= 16
    stream = "\n".join(ops).encode("latin-1", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(obj)
        out.write(b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(b"trailer\n")
    out.write(f"<< /Size {len(objs) + 1} /Root 1 0 R >>\n".encode())
    out.write(f"startxref\n{xref_pos}\n%%EOF\n".encode())
    path.write_bytes(out.getvalue())


def build_table_pdf(text_lines: list[str], table_rows: list[list[str]], path: Path, ruled: bool = False) -> None:
    """PDF con testo libero + tabella a colonne allineate (per il table detector).

    Con `ruled=True` la tabella è circondata da una griglia di linee (per
    testare la detection PyMuPDF `find_tables(strategy='lines')`).
    """
    esc = lambda s: s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")  # noqa: E731
    ops = []
    y = 740
    for t in text_lines:
        ops.append(f"BT /F1 11 Tf 56 {y} Td ({esc(t)}) Tj ET")
        y -= 18
    y -= 8
    if ruled:
        x0 = 56
        cell_w = 105
        n = len(table_rows)
        n_cols = len(table_rows[0])
        top = y + 12
        bottom = y - 16 * (n - 1) - 8
        ops.append("q 0.6 w")
        for k in range(n + 1):
            ly = top - 16 * k
            ops.append(f"{x0} {ly} m {x0 + cell_w * n_cols} {ly} l S")
        for k in range(n + 1):
            lx = x0 + cell_w * k
            ops.append(f"{lx} {top} m {lx} {bottom} l S")
        ops.append("Q")
        for row in table_rows:
            x = x0 + 6
            for cell in row:
                ops.append(f"BT /F1 10 Tf {x} {y} Td ({esc(cell)}) Tj ET")
                x += cell_w
            y -= 16
    else:
        for row in table_rows:
            x = 56
            for cell in row:
                ops.append(f"BT /F1 10 Tf {x} {y} Td ({esc(cell)}) Tj ET")
                x += 130
            y -= 16
    stream = "\n".join(ops).encode("latin-1", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(obj)
        out.write(b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(b"trailer\n")
    out.write(f"<< /Size {len(objs) + 1} /Root 1 0 R >>\n".encode())
    out.write(f"startxref\n{xref_pos}\n%%EOF\n".encode())
    path.write_bytes(out.getvalue())


def build_simple_docx(path: Path) -> None:
    """DOCX minimale (OOXML) con heading e paragrafi."""
    xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Vector Databases</w:t></w:r></w:p>
    <w:p><w:r><w:t>A vector database stores embeddings for similarity search.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Indexing</w:t></w:r></w:p>
    <w:p><w:r><w:t>An inverted index maps terms to documents.</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="xml" ContentType="application/xml"/>
</Types>""")
        zf.writestr("word/document.xml", xml)


def build_scanned_pdf(path: Path, lines: list[str] | None = None) -> None:
    """PDF con UNA SOLA pagina immagine, zero layer testuale: simula una
    scansione/fax (il motore built-in non può estrarre nulla)."""
    from PIL import Image, ImageDraw

    default_lines = [
        "CONTRATTO DI APPALTO - Rep. 42/2026",
        "Art. 1 - Oggetto",
        "Il presente contratto ha ad oggetto la fornitura",
        "di arredi per gli uffici dell'amministrazione.",
        "Art. 2 - Importo",
        "L'importo complessivo e' di Euro 12.800,00.",
    ]
    txt = lines or default_lines
    img = Image.new("RGB", (1240, 1600), "white")
    d = ImageDraw.Draw(img)
    y = 80
    for ln in txt:
        d.text((80, y), ln, fill="black")
        y += 44
    img.save(path, "PDF")


@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    p = tmp_path / "sales.csv"
    rows = ["revenue,units,region"]
    import random

    random.seed(42)
    for i in range(40):
        units = random.randint(10, 100)
        revenue = round(units * random.uniform(8, 14), 2)
        region = "N" if i % 2 else "S"
        rows.append(f"{revenue},{units},{region}")
    p.write_text("\n".join(rows), encoding="utf-8")
    return p


@pytest.fixture()
def sample_png(tmp_path: Path) -> Path:
    from PIL import Image

    p = tmp_path / "diagram.png"
    img = Image.new("RGB", (320, 200), (250, 250, 255))
    for x in range(0, 320, 20):
        for y in range(0, 200, 20):
            img.putpixel((x, y), (30, 90, 200))
    img.save(p, "PNG")
    return p


@pytest.fixture()
def sample_sqlite(tmp_path: Path) -> Path:
    p = tmp_path / "users.sqlite"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE users(id INTEGER, age INTEGER, score REAL)")
    con.executemany(
        "INSERT INTO users VALUES (?,?,?)",
        [(i, 20 + i % 40, i * 1.5) for i in range(1, 25)],
    )
    con.commit()
    con.close()
    return p
