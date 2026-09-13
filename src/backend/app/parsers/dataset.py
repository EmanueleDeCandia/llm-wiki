"""Profiling dataset tabellari con Polars (Skill §1.4 e §4-A.3).

Invariante: i dataset NON vengono mai serializzati in tabelle Markdown
completa. Il parser produce un *profilo* (schema, statistiche descrittive,
matrice di correlazione, prime righe rappresentative) che il compilatore
trasforma in una scheda metadati `wiki/entities/{dataset}.md`.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

import polars as pl


@dataclass
class ColumnProfile:
    name: str
    dtype: str
    null_count: int
    distinct: int
    stats: dict = field(default_factory=dict)


@dataclass
class DatasetProfile:
    source_path: str
    name: str
    engine: str
    rows: int
    columns: list[ColumnProfile]
    correlations: dict[str, dict[str, float]]
    sample_records: list[dict]
    error: str | None = None

    @property
    def dtypes(self) -> dict[str, str]:
        return {c.name: c.dtype for c in self.columns}

    def to_dict(self) -> dict:
        return asdict(self)


class DatasetParser:
    name = "dataset"

    def profile(self, path: Path, vault_rel: str) -> DatasetProfile:
        suffix = path.suffix.lower()
        name = path.stem
        try:
            if suffix in (".csv", ".tsv"):
                df = pl.read_csv(path, separator="\t" if suffix == ".tsv" else ",")
                engine = "polars-csv"
            elif suffix == ".parquet":
                df = pl.read_parquet(path)
                engine = "polars-parquet"
            elif suffix in (".sqlite", ".db", ".sqlite3"):
                df = self._read_sqlite(path)
                engine = "polars-sqlite"
            else:
                return DatasetProfile(vault_rel, name, "unsupported", 0, [], [], [],
                                      error=f"Formato non supportato: {suffix}")
        except Exception as exc:  # noqa: BLE001
            return DatasetProfile(vault_rel, name, "polars", 0, [], [], [], error=str(exc))

        return self._build_profile(df, vault_rel, name, engine)

    @staticmethod
    def _read_sqlite(path: Path) -> pl.DataFrame:
        con = sqlite3.connect(path)
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )]
            frames: list[pl.DataFrame] = []
            for t in tables:
                cur = con.execute(f'SELECT * FROM "{t}" LIMIT 1000000')
                cols = [d[0] for d in cur.description]
                frames.append(pl.from_records(cur.fetchall(), schema=cols, orient="row"))
            return pl.concat(frames) if frames else pl.DataFrame()
        finally:
            con.close()

    def _build_profile(self, df: pl.DataFrame, vault_rel: str, name: str, engine: str) -> DatasetProfile:
        rows = len(df)
        cols: list[ColumnProfile] = []
        for col in df.columns:
            s = df[col]
            dtype = str(s.dtype)
            nulls = int(s.null_count())
            distinct = int(s.n_unique())
            stats: dict = {}
            if s.dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8,
                           pl.UInt16, pl.UInt32, pl.UInt64, pl.Float32, pl.Float64):
                stats = {
                    "min": _num(s.min()),
                    "max": _num(s.max()),
                    "mean": _round(s.mean()),
                    "std": _round(s.std()),
                    "median": _round(s.median()),
                    "p25": _round(s.quantile(0.25)),
                    "p75": _round(s.quantile(0.75)),
                }
            elif dtype == "str":
                lengths = s.cast(pl.String).str.len_chars()
                stats = {"avg_len": _round(lengths.mean())}
            cols.append(ColumnProfile(col, dtype, nulls, distinct, stats))

        correlations = self._correlations(df)
        sample = df.head(5).to_dicts() if rows else []
        # Sanitize: i valori non JSON-serializzabili diventano stringhe.
        sample = [{k: _jsonable(v) for k, v in rec.items()} for rec in sample]
        return DatasetProfile(vault_rel, name, engine, rows, cols, correlations, sample)

    @staticmethod
    def _correlations(df: pl.DataFrame, max_cols: int = 12) -> dict[str, dict[str, float]]:
        """Correlazione di Pearson calcolata in pure Polars (no pyarrow/pandas)."""
        import math

        numeric = [c for c in df.columns
                   if df[c].dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                                      pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                                      pl.Float32, pl.Float64)][:max_cols]
        if len(numeric) < 2:
            return {}

        def pearson(a: str, b: str) -> float | None:
            sub = pl.DataFrame({a: df[a].cast(pl.Float64), b: df[b].cast(pl.Float64)}).drop_nulls()
            n = len(sub)
            if n < 2:
                return None
            ma, mb = sub[a].mean(), sub[b].mean()
            dx, dy = sub[a] - ma, sub[b] - mb
            den = math.sqrt(float((dx * dx).sum()) * float((dy * dy).sum()))
            if not den:
                return None
            return float((dx * dy).sum()) / den

        out: dict[str, dict[str, float]] = {}
        for i, a in enumerate(numeric):
            out[a] = {}
            for b in numeric[i + 1:]:
                v = pearson(a, b)
                if v is not None and v == v:
                    out[a][b] = round(v, 4)
        return out


def _num(x) -> float | None:
    return None if x is None or x != x else float(x)


def _round(x) -> float | None:
    v = _num(x)
    return None if v is None else round(v, 4)


def _jsonable(v):
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return str(v)
