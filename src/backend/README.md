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
| `app/parsers/` | Parser multimodali (PDF pypdf/docling hook, TXT/MD, DOCX OOXML, PNG Pillow, CSV/Parquet/SQLite polars) — §4-A |
| `app/compiler/` | Compilazione note atomiche: `DeterministicCompiler` (by-default, **senza AI**) e `LLMCompiler` (stesso contratto, prompt in `prompts.py`) — §4-A.4 |
| `app/index/` | Generatore `_index/INDEX.md` + `_index/graph.json` — §4-A.4 |
| `app/lint/` | Pipeline B: grafo G=(V,E), link orfani, nodi isolati, cluster, conflitti, `lint_report.md` — §4-B |
| `app/sandbox/` | Pipeline C: kernel subprocess isolato (`python -I`), timeout 30 s, figure → `sources/images/generated/` — §4-C |
| `app/llm/` | **LLM Abstraction Layer**: `LLMClient` + adattatori OpenAI/Anthropic/Ollama + client offline. `LLM_PROVIDER=none` (default): nessun modello invocato — §5.2 |
| `app/agent/` | Interrogazione note: retrieval deterministico (by-default) o sintesi LLM — §6 |
| `app/api/routes.py` | Endpoint §6: `vault/open`, `ingest/file`, `graph/nodes`, `lint/run`, `sandbox/run`, `agent/query` + supporto UI |

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
