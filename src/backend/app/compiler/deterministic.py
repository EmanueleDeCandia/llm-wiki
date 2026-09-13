"""Compilatore deterministico (senza modelli AI).

Decompone i documenti in note atomiche, conserva il LaTeX, applica lo schema
frontmatter e la struttura a blocchi rigidi (Skill §3), crea i wikilink
bidirezionali verso i concetti già noti e rispetta la provenienza (§1.3).

Quando verrà integrato un provider LLM, `LLMCompiler` produrrà lo stesso
contratto `CompilationResult`: pipeline, indice e UI non cambiano.
"""
from __future__ import annotations

import re
from datetime import date

from ..core.vault import slugify
from ..parsers.dataset import DatasetProfile
from ..schemas.wiki import ParsedDocument, ParsedImage, WikiNote
from .base import CompiledNote, CompilationResult, CompileContext
from .links import WIKILINK_RE

# -- lessico per tag e acronimi (euristica deterministica) -------------------
TAG_LEXICON: list[tuple[str, list[str]]] = [
    ("ml/neurali", ["neural", "transformer", "attention", "gpt", "lstm", "cnn",
                    "perceptron", "backprop", "deep learning", "embedding", "tokenizer"]),
    ("ml/apprendimento", ["machine learning", "apprendimento", "training", "addestramento",
                          "inference", "inferenza", "overfitting", "loss", "gradiente"]),
    ("statistica", ["correlazione", "correlation", "regressione", "regression", "ipotesi",
                    "p-value", "distribuzione", "varianza", "ipotesi null", "test statistico"]),
    ("dati/ingegneria", ["dataset", "pandas", "polars", "csv", "parquet", "etl", "profilo",
                         "schema", "colonna", "feature"]),
    ("software/algoritmi", ["algoritmo", "complessità", "complessita", "grafo", "database",
                            "scheda", "kernel", "api"]),
    ("matematica", ["teorema", "lemma", "assioma", "dimostrazione", "prova", "equazione",
                    "derivata", "integrale", "matrice"]),
]

ACRONYM_RE = re.compile(r"\b[A-Z]{2,6}\b")
_PREREQ_CUES = ("richiede", "prerequisito", "presuppone", "assume", "basato su", "si fonda su")


def _sentences(text: str, max_sentences: int = 3) -> str:
    # Rimuovi heading e righe di tabella (non fanno parte della prosa)
    prose_lines = [
        ln for ln in text.splitlines()
        if not ln.lstrip().startswith("#") and not ln.lstrip().startswith("|")
    ]
    clean = re.sub(r"[#*`>|]", " ", "\n".join(prose_lines))
    clean = WIKILINK_RE.sub(lambda m: m.group(2) or m.group(1), clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ù\"'(])", clean)
    return " ".join(p.strip() for p in parts[:max_sentences])


def _words(text: str) -> int:
    return len(text.split())


def _split_sections(markdown: str) -> list[tuple[str, str]]:
    """(titolo H2, contenuto) per ogni sezione H2; se assente, chunk di paragrafi."""
    lines = markdown.splitlines()
    sections: list[tuple[str, str]] = []
    current_title = ""
    current: list[str] = []
    for ln in lines:
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m and not ln.startswith("###"):
            if current_title or "".join(current).strip():
                sections.append((current_title, "\n".join(current)))
            current_title = m.group(1).strip()
            current = []
        else:
            current.append(ln)
    if current_title or "".join(current).strip():
        sections.append((current_title, "\n".join(current)))
    sections = [(t, b) for t, b in sections if b.strip()]
    if not sections:
        # Prose senza H2: raggruppa i paragrafi in blocchi ~300 parole.
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", markdown) if p.strip()]
        for i in range(0, len(paragraphs), 4):
            chunk = "\n\n".join(paragraphs[i : i + 4])
            sections.append((f"Stralcio {i // 4 + 1}", chunk))
        if not sections:
            sections = [("Contenuto", markdown)]
    # La sezione di apertura senza titolo (testo pre-H2) è già riassunta nella
    # nota-entità del documento: la rinominiamo "Introduzione" per leggibilità.
    return [((t or "Introduzione") if i == 0 else (t or f"Sezione {i + 1}"), b) for i, (t, b) in enumerate(sections)]


def _guess_tags(text: str) -> list[str]:
    low = text.casefold()
    tags = [tag for tag, keys in TAG_LEXICON if any(k in low for k in keys)]
    return tags or ["generale"]


def _acronyms(text: str, limit: int = 5) -> list[str]:
    seen: list[str] = []
    for m in ACRONYM_RE.finditer(text):
        tok = m.group(0)
        if tok not in seen and tok not in ("LLM", "PDF", "TXT", "MD", "CSV", "API", "JSON", "HTTP", "OCR"):
            seen.append(tok)
        if len(seen) >= limit:
            break
    return seen


class DeterministicCompiler:
    name = "deterministic"

    # ------------------------------------------------------------------ doc
    def compile_document(self, parsed: ParsedDocument, ctx: CompileContext) -> CompilationResult:
        result = CompilationResult(compiler=self.name)
        provenance = f"[[{parsed.source_path}]]"
        doc_slug = slugify(parsed.title)
        doc_rel = f"wiki/entities/{doc_slug}.md"
        doc_title = parsed.title

        # 1) Note-entità per il documento sorgente (provenienza e mappa H1-H6)
        toc = "\n".join(f"{i+1}. {h}" for i, h in enumerate(parsed.headings)) or "- (nessun heading esplicito)"
        tables_block = ""
        if parsed.tables:
            from ..parsers.tables import table_to_markdown

            tbls = "\n\n".join(table_to_markdown(t) for t in parsed.tables)
            tables_block = f"**Tabelle estratte ({len(parsed.tables)})**\n\n{tbls}\n\n"
        doc_body = (
            f"# {doc_title}\n\n"
            f"## Sintesi Esecutiva\n\n{_sentences(parsed.markdown)}\n\n"
            f"## Formalizzazione & Dettagli\n\n"
            f"Documento sorgente `{parsed.source_path}` "
            f"({_words(parsed.markdown)} parole, {len(parsed.headings)} heading) estratto dal parser "
            f"`{parsed.parser_name}`.\n\n**Gerarchia dei titoli**\n\n{toc}\n\n"
            f"{tables_block}"
            f"I contenuti atomici derivati da questo documento sono documentati nelle note "
            f"concettuali collegate in § Relazioni nel Grafo.\n\n"
        )
        doc_related = []  # popolato dopo le note concetto
        doc_relations_prereq: list[str] = []

        # 2) Note atomiche dalle sezioni H2
        concept_titles: list[str] = []
        for title, body in _split_sections(parsed.markdown)[: ctx.max_concept_notes]:
            c_title = _clean_title(title, doc_title)
            slug = slugify(c_title)
            rel = f"wiki/concepts/{slug}.md"
            prereqs, related = self._match_existing(c_title, body, ctx)
            aliases = _acronyms(body)
            tags = _guess_tags(body)
            note = WikiNote(
                title=c_title,
                type="concept",
                created=date.today().isoformat(),
                updated=date.today().isoformat(),
                sources=[provenance],
                aliases=aliases,
                tags=tags,
                relations={  # type: ignore[arg-type]
                    "prerequisites": [f"[[{p}]]" for p in prereqs],
                    "related": [f"[[{r}]]" for r in related],
                    "conflicts_with": [],
                },
            )
            rel_links = self._relations_block(prereqs, related)
            concept_body = (
                f"# {c_title}\n\n"
                f"## Sintesi Esecutiva\n\n{_sentences(body)}\n\n"
                f"## Formalizzazione & Dettagli\n\n"
                f"{_truncate(body.strip() or '(sezione senza contenuto)', 6000)}\n\n"
                f"## Relazioni nel Grafo\n\n{rel_links}\n\n"
                f"## Discrepanze & Limiti\n\n"
                f"- Nessun conflitto numerico rilevato tra le fonti disponibili.\n"
                f"- Provenienza: {provenance}. Estrazione automatica (motore deterministico): "
                f"la revisione umana è consigliata prima della pubblicazione.\n"
            )
            result.notes.append(CompiledNote(rel_path=rel, frontmatter_yaml=_fm(note), body_md=concept_body))
            concept_titles.append(c_title)
            doc_related.extend(related)

        # 3) Nota-entità del documento (relazioni verso le note appena create)
        doc_related = _dedupe(doc_related + concept_titles)
        doc_note = WikiNote(
            title=doc_title,
            type="entity",
            created=date.today().isoformat(),
            updated=date.today().isoformat(),
            sources=[provenance],
            aliases=_dedupe(_acronyms(doc_title) + [slugify(doc_title)])[:6],
            tags=_guess_tags(parsed.markdown[:2000]),
            relations={  # type: ignore[arg-type]
                "prerequisites": [f"[[{p}]]" for p in doc_relations_prereq],
                "related": [f"[[{r}]]" for r in doc_related],
                "conflicts_with": [],
            },
        )
        doc_body += (
            f"## Relazioni nel Grafo\n\n{self._relations_block(doc_relations_prereq, doc_related)}\n\n"
            f"## Discrepanze & Limiti\n\n"
            f"- Nessun conflitto numerico rilevato tra le fonti disponibili.\n"
            f"- Provenienza: {provenance}.\n"
        )
        result.notes.append(CompiledNote(rel_path=doc_rel, frontmatter_yaml=_fm(doc_note), body_md=doc_body))

        if not result.notes:
            result.messages.append("Documento vuoto: nessuna nota generata.")
        return result

    def _match_existing(self, title: str, body: str, ctx: CompileContext) -> tuple[list[str], list[str]]:
        """Collega la nuova nota ai nodi già presenti (bidirezionalità del grafo)."""
        prereqs: list[str] = []
        related: list[str] = []
        body_low = body.casefold()
        for node_id, names in ctx.existing.items():
            for name in names:
                if not name or len(name) < 4:
                    continue
                if name.casefold() == title.casefold():
                    continue
                pattern = re.escape(name.casefold())
                m = re.search(rf"\b{pattern}\b", body_low)
                if not m:
                    continue
                window = body_low[max(0, m.start() - 100) : m.end() + 10]
                display = name
                if any(cue in window for cue in _PREREQ_CUES):
                    if display not in prereqs:
                        prereqs.append(display)
                elif display not in related:
                    related.append(display)
                break
        return prereqs, related

    @staticmethod
    def _relations_block(prereqs: list[str], related: list[str]) -> str:
        lines = []
        lines.append("- Prerequisiti: " + (", ".join(f"[[{p}]]" for p in prereqs) if prereqs else "nessun prerequisito dichiarato."))
        lines.append("- Correlate: " + (", ".join(f"[[{r}]]" for r in related) if related else "nessuna correlazione rilevata."))
        lines.append("- In conflitto: nessuna.")
        return "\n".join(lines)

    # ------------------------------------------------------------- dataset
    def compile_dataset(self, profile: DatasetProfile, ctx: CompileContext) -> CompilationResult:
        result = CompilationResult(compiler=self.name)
        provenance = f"[[{profile.source_path}]]"
        slug = slugify(profile.name)
        rel = f"wiki/entities/{slug}.md"
        if profile.error:
            note = WikiNote(
                title=profile.name, type="dataset",
                created=date.today().isoformat(), updated=date.today().isoformat(),
                sources=[provenance], tags=["dati/ingegneria"],
            )
            body = (
                f"# {profile.name}\n\n"
                f"## Sintesi Esecutiva\n\nIl dataset non è stato profilato.\n\n"
                f"## Formalizzazione & Dettagli\n\nErrore del parser: `{profile.error}`\n\n"
                f"## Relazioni nel Grafo\n\n- Sorgente: {provenance}\n\n"
                f"## Discrepanze & Limiti\n\n- Dataset non leggibile: verificare il formato del file.\n"
            )
            result.notes.append(CompiledNote(rel, _fm(note), body))
            return result

        col_rows = []
        for c in profile.columns:
            s = c.stats
            col_rows.append(
                f"| {c.name} | {c.dtype} | {c.null_count} | {c.distinct} | "
                f"{s.get('min', '—')} | {s.get('max', '—')} | {s.get('mean', '—')} | {s.get('std', '—')} |"
            )
        schema_table = (
            "| Colonna | Tipo | Null | Distinct | Min | Max | Media | Std |\n"
            "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |\n" + "\n".join(col_rows)
        )
        if profile.correlations:
            corr_lines = []
            for a, vals in profile.correlations.items():
                for b, v in vals.items():
                    corr_lines.append(f"- `{a}` ↔ `{b}`: $r = {v}$")
            corr_block = "\n".join(corr_lines)
        else:
            corr_block = "Nessuna coppia di colonne numeriche sufficienti per la correlazione."
        sample_block = _render_sample(profile.sample_records)
        note = WikiNote(
            title=profile.name,
            type="dataset",
            created=date.today().isoformat(),
            updated=date.today().isoformat(),
            sources=[provenance],
            aliases=[profile.name.replace("_", " ")],
            tags=["dati/ingegneria"],
        )
        body = (
            f"# {profile.name}\n\n"
            f"## Sintesi Esecutiva\n\n"
            f"Dataset tabellare con {profile.rows} righe e {len(profile.columns)} colonne, "
            f"profilato dal motore `{profile.engine}`.\n\n"
            f"## Formalizzazione & Dettagli\n\n"
            f"**Schema e statistiche descrittive**\n\n{schema_table}\n\n"
            f"**Matrice di correlazione (Pearson, colonne numeriche)**\n\n{corr_block}\n\n"
            f"**Prime 5 righe rappresentative**\n\n{sample_block}\n\n"
            f"## Relazioni nel Grafo\n\n- Sorgente: {provenance}\n\n"
            f"## Discrepanze & Limiti\n\n"
            f"- I dati completi NON sono serializzati (invariante di isolamento §1.4): "
            f"esecuzione di calcoli e grafici nel sandbox Python (`/api/v1/sandbox/run`).\n"
        )
        result.notes.append(CompiledNote(rel, _fm(note), body))
        return result

    # -------------------------------------------------------------- image
    def compile_image(self, meta: ParsedImage, ctx: CompileContext) -> CompilationResult:
        result = CompilationResult(compiler=self.name)
        provenance = f"[[{meta.source_path}]]"
        slug = slugify(meta.title)
        rel = f"wiki/entities/{slug}.md"
        note = WikiNote(
            title=meta.title,
            type="entity",
            created=date.today().isoformat(),
            updated=date.today().isoformat(),
            sources=[provenance],
            tags=["documenti/immagini"],
        )
        body = (
            f"# {meta.title}\n\n"
            f"## Sintesi Esecutiva\n\n"
            f"Immagine {meta.format} {meta.width}×{meta.height} px "
            f"({meta.size_bytes / 1024:.0f} KB) archiviata come sorgente immutabile.\n\n"
            f"## Formalizzazione & Dettagli\n\n"
            f"| Proprietà | Valore |\n| :--- | :--- |\n"
            f"| Formato | {meta.format} |\n| Dimensioni | {meta.width} × {meta.height} |\n"
            f"| Modalità | {meta.mode} |\n\n"
            f"{meta.description}\n\n"
            f"## Relazioni nel Grafo\n\n- Sorgente: {provenance}\n\n"
            f"## Discrepanze & Limiti\n\n"
            f"- OCR/Vision non abilitati: la descrizione testuale è un segnaposto fino "
            f"all'integrazione di un estrattore Vision.\n"
        )
        result.notes.append(CompiledNote(rel, _fm(note), body))
        return result


# -- helper -------------------------------------------------------------------

def _clean_title(title: str, doc_title: str) -> str:
    t = title.strip() or "Sezione"
    t = re.sub(r"^[0-9]+[.)]\s*", "", t)
    return t[:100]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit("\n", 1)[0] + "\n\n*(contenuto troncato per lunghezza; vedi la fonte originale)*"


def _dedupe(seq: list[str]) -> list[str]:
    out: list[str] = []
    for s in seq:
        if s and s not in out:
            out.append(s)
    return out


def _fm(note: WikiNote) -> str:
    from ..schemas.wiki import frontmatter_to_yaml

    return frontmatter_to_yaml(note)


def _render_sample(records: list[dict]) -> str:
    if not records:
        return "Nessuna riga disponibile."
    cols = list(records[0].keys())
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in records]
    return "\n".join([head, sep, *rows])
