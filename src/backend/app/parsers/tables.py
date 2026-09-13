"""Estrazione di tabelle da PDF digitali senza modelli ML.

Approccio deterministico basato sul *layout*: le posizioni dei fragmenti di
testo (via `pypdf` visitor) vengono raggruppate in righe (clustering su Y) e
le righe consecutive con colonne allineate (2+ posizioni X condivise)
vengono promosse a tabella Markdown. Non richiede AI né dipendenze esterne:
è il fallback del motore `docling` quando quest'ultimo non è disponibile.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..schemas.wiki import ParsedTable

X_TOL = 3.0      # tolleranza allineamento colonne (pt)
Y_TOL = 2.5      # tolleranza clustering righe (pt)
ROW_GAP = 30.0   # massimo gap verticale tra righe di una tabella (pt)
MIN_COLS = 2     # colonne minime perché una regione sia "tabella"
MIN_ROWS = 2     # righe minime (header + 1)


@dataclass
class Span:
    x: float
    y: float
    text: str


@dataclass
class Row:
    y: float
    spans: list[Span] = field(default_factory=list)


def spans_to_rows(spans: list[Span]) -> list[Row]:
    rows: list[Row] = []
    for sp in sorted(spans, key=lambda s: (-s.y, s.x)):
        if rows and abs(rows[-1].y - sp.y) <= Y_TOL:
            rows[-1].spans.append(sp)
        else:
            rows.append(Row(y=sp.y, spans=[sp]))
    for r in rows:
        r.spans.sort(key=lambda s: s.x)
    return rows


def _cluster_values(values: list[float], tol: float) -> list[float]:
    out: list[float] = []
    for v in sorted(values):
        if out and v - out[-1] <= tol:
            out[-1] = (out[-1] + v) / 2
        else:
            out.append(v)
    return out


def _aligned(a: list[float], b: list[float], tol: float) -> bool:
    """True se le due liste di colonne condividono gli stessi punti (±tol)."""
    for x in a:
        if not any(abs(x - y) <= tol for y in b):
            return False
    for y in b:
        if not any(abs(x - y) <= tol for x in a):
            return False
    return True


def _col_index(x: float, cols: list[float], tol: float) -> int:
    idx = 0
    for i, c in enumerate(cols):
        if x >= c - tol:
            idx = i
        else:
            break
    return idx


def detect_tables(rows: list[Row]) -> list[tuple[int, int, list[float]]]:
    """Ritorna (start, end, colonne) per ogni regione tabellare consecutiva."""
    tables: list[tuple[int, int, list[float]]] = []
    i, n = 0, len(rows)
    while i < n:
        cols: list[float] | None = None
        j = i
        while j < n:
            r = rows[j]
            if len(r.spans) < 2:
                break
            if j > i and (rows[j - 1].y - r.y) > ROW_GAP:
                break
            xs = _cluster_values([s.x for s in r.spans], X_TOL)
            if cols is None:
                if len(xs) < MIN_COLS:
                    break
                cols = xs
            elif not _aligned(xs, cols, X_TOL):
                break
            j += 1
        if cols is not None and j - i >= MIN_ROWS:
            tables.append((i, j, cols))
            i = j
        else:
            i += 1
    return tables


def extract_tables_from_spans(spans: list[Span]) -> tuple[list[ParsedTable], set[int]]:
    """Estrae le tabelle e restituisce anche gli indici di riga coinvolti."""
    rows = spans_to_rows(spans)
    tables: list[ParsedTable] = []
    row_indices: set[int] = set()
    for start, end, cols in detect_tables(rows):
        grid: list[list[str]] = []
        for r in rows[start:end]:
            cells = [""] * len(cols)
            for s in r.spans:
                ci = _col_index(s.x, cols, X_TOL)
                cells[ci] = (cells[ci] + " " + s.text).strip()
            grid.append(cells)
        header, *body = grid
        tables.append(ParsedTable(header=header, rows=body))
        row_indices.update(range(start, end))
    return tables, row_indices


def table_to_markdown(table: ParsedTable) -> str:
    cols = len(table.header)
    lines = [
        "| " + " | ".join(table.header) + " |",
        "| " + " | ".join(_aligns(table, cols)) + " |",
    ]
    for row in table.rows:
        padded = list(row) + [""] * (cols - len(row))
        lines.append("| " + " | ".join(padded[:cols]) + " |")
    return "\n".join(lines)


def _aligns(table: ParsedTable, cols: int) -> list[str]:
    aligns = []
    for c in range(cols):
        # solo le righe dati (non l'header) contano per il tipo numerico
        values = [r[c] for r in table.rows if c < len(r) and r[c].strip()]
        if values and all(re.fullmatch(r"-?[\d.,]+", v.strip()) for v in values):
            aligns.append("---:")
        else:
            aligns.append(":---")
    return aligns


def parse_markdown_table(md: str) -> ParsedTable | None:
    """Converte una tabella Markdown semplice in ParsedTable (per i docling)."""
    lines = [ln.strip() for ln in md.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        return None

    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip("|").split("|")]

    header = cells(lines[0])
    body: list[list[str]] = []
    for ln in lines[1:]:
        row = cells(ln)
        if all(re.fullmatch(r":?-{3,}:?", c) for c in row if c):
            continue  # riga di separazione
        body.append(row)
    return ParsedTable(header=header, rows=body)
