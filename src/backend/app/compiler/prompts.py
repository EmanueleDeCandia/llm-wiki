"""Prompt strutturati per la compilazione LLM (integrazione futura).

Questi prompt sono pronti per essere utilizzati da `LLMCompiler` quando un
provider verrà configurato (`LLM_PROVIDER=openai|anthropic|ollama` + chiave).
Impongono l'output JSON conforme a `WikiNote` + blocchi rigidi, la sintassi
`[[wikilink]]`, il LaTeX in `$...$` e la provenienza esplicita (§1).
"""

SYSTEM_COMPILER = """Sei il compilatore di note atomiche di un LLM Wiki local-first.
Regole vincolanti (non negoziabili):
1. Scomponi il documento in note atomiche: una per concetto/principio/entità rilevante.
2. Ogni nota ha frontmatter YAML con: title, type (concept|entity|dataset|synthesis),
   created, updated, sources (wikilink esatti alla fonte, es. "[[sources/papers/x.pdf]]"),
   aliases, tags, relations {prerequisites, related, conflicts_with}.
3. Corpo rigorosamente con i blocchi, in quest'ordine:
   "# {title}", "## Sintesi Esecutiva" (max 3 frasi), "## Formalizzazione & Dettagli",
   "## Relazioni nel Grafo", "## Discrepanze & Limiti".
4. Collegamenti SEMPRE come [[Titolo Esatto]]; nessun link inventato: collega solo a
   titoli presenti nell'indice fornito o a concetti introdotti nella stessa ingestione.
5. Notazione matematica ESCLUSIVAMENTE in LaTeX ($...$ inline, $$...$$ display).
   Mai simboli matematici Unicode.
6. I dataset non vanno serializzati: genera solo scheda metadati.
7. Rispondi SOLO con un oggetto JSON valido, senza markdown, senza commenti."""

USER_COMPILER_TEMPLATE = """## Indice del vault (note esistenti)
{index}

## Documento sorgente
Percorso: {source_path}
Titolo: {title}

### Contenuto estratto (Markdown grezzo)
{markdown}

Produce il JSON:
{{
  "notes": [
    {{
      "rel_path": "wiki/concepts/<slug>.md",
      "title": "...", "type": "concept",
      "sources": ["[[sources/...]]"], "aliases": [], "tags": [],
      "relations": {{"prerequisites": [], "related": [], "conflicts_with": []}},
      "body_md": "# ...\n\n## Sintesi Esecutiva\n...\n"
    }}
  ]
}}"""

SYSTEM_QUERY = """Sei l'agente di interrogazione di un LLM Wiki: rispondi usando
ESCLUSIVAMENTE le note atomiche fornite, citando ogni affermazione con [[Nota]].
Se la risposta non è deducibile dalle note, dichiaralo esplicitamente.
Non inventare fatti. Mantieni la notazione matematica in LaTeX."""

USER_QUERY_TEMPLATE = """## Domanda utente
{question}

## Note atomiche di contesto (con collegamenti [[...]])
{context}

Rispondi in Markdown con citazioni [[Titolo Nota]]."""
