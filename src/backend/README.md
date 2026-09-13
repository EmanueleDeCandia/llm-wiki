# Backend — LLM Wiki Engine (FastAPI sidecar)

Runtime Python 3.11+ con FastAPI/Uvicorn, avviato come sidecar locale
(porta `8100`) dal frontend (Vite in sviluppo, Tauri in produzione).

## Avvio

```bash
cd src/backend
# venv già creato in <repo>/.venv (o: python3 -m venv .venv)
../../.venv/bin/pip install -r requirements.txt
../../.venv/bin/python run.py
# oppure: API_PORT=8100 ../../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
```

Documentazione API interattiva: `http://127.0.0.1:8100/docs`.

## Test

```bash
cd src/backend && ../../.venv/bin/python -m pytest
```

## Architettura interna

| Modulo | Responsabilità (Skill) |
| :--- | :--- |
| `app/core/vault.py` | Topologia del vault, apertura, **immutabilità `sources/`** (hash SHA-256) — §1-2 |
| `app/schemas/wiki.py` | `WikiSchema`: frontmatter YAML + blocchi rigidi del corpo — §3 |
| `app/parsers/` | Parser multimodali (PDF engine `auto` = docling → pypdf+tables, TXT/MD, DOCX OOXML, PNG Pillow, CSV/Parquet/SQLite polars) — §4-A |
| `app/compiler/` | Compilazione note atomiche: `DeterministicCompiler` (by-default, **senza AI**) e `LLMCompiler` (stesso contratto, prompt in `prompts.py`) — §4-A.4 |
| `app/index/` | Generatore `_index/INDEX.md` + `_index/graph.json` — §4-A.4 |
| `app/lint/` | Pipeline B: grafo G=(V,E), link orfani, nodi isolati, cluster, conflitti, `lint_report.md` — §4-B |
| `app/sandbox/` | Pipeline C: kernel subprocess isolato (`python -I`), timeout 30 s, figure → `sources/images/generated/` — §4-C |
| `app/llm/` | **LLM Abstraction Layer**: `LLMClient` + adattatori OpenAI/Anthropic/Ollama + client offline. `LLM_PROVIDER=none` (default): nessun modello invocato — §5.2 |
| `app/agent/` | Interrogazione note: retrieval deterministico (by-default) o sintesi LLM — §6 |
| `app/api/routes.py` | Endpoint §6: `vault/open`, `ingest/file`, `graph/nodes`, `lint/run`, `sandbox/run`, `agent/query` + supporto UI |

## Parser PDF: selezione del motore

`LLW_PDF_ENGINE` (default `auto`):

| Valore | Comportamento |
| :--- | :--- |
| `auto` | Catena: `docling` (se installato) → `llamaparse` cloud (se `LLAMAPARSE_API_KEY` è configurata) → built-in. Ogni passaggio è loggato; nessun errore a metà pipeline |
| `pypdf` | Motore built-in, zero AI: testo dal layer testuale + **due livelli di table detection** — PyMuPDF `find_tables` (PDF con linee di separazione, incluso booktabs) ed euristica su coordinate per tabelle allineate senza linee → tabelle Markdown con allineamento numerico |
| `docling` / `marker` | Vincolati all'engine indicato (fallback built-in solo in caso di errore) |
| `llamaparse` | API cloud LlamaIndex: Markdown con tabelle e formule LaTeX. **Il PDF lascia la macchina** — solo documenti non sensibili. Richiede `LLAMAPARSE_API_KEY` |

Per attivare docling su una macchina con internet:

```bash
pip install docling          # la modalità auto lo usa automaticamente
# opzionale: formule in LaTeX vero
# LLW_PDF_FORMULAS=1
```

Le tabelle estratte vengono inserite nella nota-entità del documento
(blocco `Tabelle estratte`) e rese disponibili in `ParsedDocument.tables`
per pipeline future. Il frontmatter/note restano sempre generate dal
compiler deterministico: gli engine (anche cloud) fanno solo la
conversione PDF → Markdown.

## Integrazione modelli AI (quando serve)

L'applicazione non contiene modelli né agenti AI: opera con un motore
deterministico. Per abilitare la sintesi semantica basta:

1. `cp .env.example .env`
2. impostare `LLM_PROVIDER=openai|anthropic|ollama` e le credenziali
   (o avviare un server Ollama locale);
3. riavviare il sidecar.

Niente altro da cambiare: `compiler/llm_compiler.py`, `agent/query_service.py`
e i prompt in `compiler/prompts.py` consumano automaticamente il client
configurato mantenendo schema, provenienza e grafo invariati.
