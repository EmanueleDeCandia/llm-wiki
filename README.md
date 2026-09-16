<div align="center">

# 🧠 LLM Wiki Desktop

### *Piattaforma Desktop Local-First per la Gestione Avanzata della Conoscenza Compilata*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tauri](https://img.shields.io/badge/Tauri-2.0-blue?logo=tauri&logoColor=white)](https://tauri.app/)
[![React](https://img.shields.io/badge/React-18%2B-61DAFB?logo=react&logoColor=black)](https://reactjs.org/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Sidecar-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Obsidian Compatible](https://img.shields.io/badge/Obsidian-Compatible-7C3AED?logo=obsidian&logoColor=white)](https://obsidian.md)

<p align="center">
  <a href="#-visione-llm-wiki-vs-rag">Visione</a> •
  <a href="#-funzionalità-chiave">Funzionalità</a> •
  <a href="#-topologia-del-vault">Topologia Vault</a> •
  <a href="#-architettura-di-sistema">Architettura</a> •
  <a href="#-installazione--setup">Installazione</a> •
  <a href="#-workflow-operativi">Workflow</a> •
  <a href="#-integrazione-agenti-skillmd">Agent Skills</a>
</p>

---

</div>

> *"I documenti grezzi sono gli ingredienti. L'LLM Wiki è il piatto cucinato. Con il RAG convenzionale cucini da capo ogni singola volta che hai fame."*  
> — **Andrej Karpathy**

---

## 🏁 Stato di implementazione (questa versione)

L'applicazione è **completamente funzionante senza modelli né agenti AI**:
tutte le pipeline sono eseguite da un motore deterministico (parser,
compilazione, lint, sandbox, retrieval). Il layer LLM (OpenAI / Anthropic /
Ollama) è presente come **adattatore opzionale** e si attiva solo con
configurazione esplicita — zero inferenze in assenza di `LLM_PROVIDER`.

| Componente | Stato |
| :--- | :--- |
| Vault (topologia, immutabilità `sources/`, provenienza) | ✅ implementato + test |
| Pipeline A — Ingestione (PDF/TXT/MD/DOCX, immagini, CSV/Parquet/SQLite) → note atomiche + `[[wikilink]]` + `INDEX.md` + `graph.json` | ✅ implementato + test |
| PDF engine — `auto`: `docling` → `llamaparse` cloud (se chiave configurata) → built-in **pypdf+PyMuPDF+tables** (tabelle con linee + euristica layout, zero AI) | ✅ implementato + test |
| Pipeline B — Knowledge Linting (orfani, isolati, cluster, conflitti, `lint_report.md`) | ✅ implementato + test |
| Pipeline C — Sandbox Python (kernel isolato, 30 s, figure, note di sintesi) | ✅ implementato + test |
| Frontend 3 colonne (tree, editor KaTeX+wikilink, grafo force-directed, console, lint, query) | ✅ React + TS + Tailwind |
| API FastAPI (endpoint Skill §6) | ✅ implementato + test (34 test) |
| LLM Abstraction Layer (client unificato + provider) | ✅ pronto, **disattivato by default** |
| Shell Tauri desktop | 🔜 scaffold in `src/frontend/tauri/` (packaging successivo) |

### Setup rapido

```bash
# 1) Backend (sidecar FastAPI, porta 8100)
cd src/backend
python3 -m venv ../../.venv
../../.venv/bin/pip install -r requirements.txt
../../.venv/bin/python run.py

# 2) Frontend (Vite, porta 5173, proxy /api → 8100)
cd src/frontend
npm install
npm run dev

# 3) Apri http://localhost:5173 e usa "✨ Vault demo"
#    oppure "python -m pytest" in src/backend per la suite di conformità
```

### Abilitare un modello AI (quando serve)

```bash
cd src/backend && cp .env.example .env
# nel .env: LLM_PROVIDER=anthropic (+ ANTHROPIC_API_KEY)
# oppure LLM_PROVIDER=ollama + un server Ollama locale (modello offline)
```

Nessuna modifica al codice: compilatore, agent e UI passano automaticamente
dalla sintesi deterministica a quella LLM mantenendo invariati schema,
provenienza e grafo.

---

## 📖 Visione: LLM Wiki vs RAG Tradizionale

I sistemi RAG (*Retrieval-Augmented Generation*) tradizionali soffrono di limiti strutturali insormontabili quando applicati a basi di conoscenza complesse:
* **Frammentazione cieca**: Il chunking arbitrario a 500-1000 token spezza argomentazioni, logiche matematiche e tabelle.
* **Tassa computazionale a ogni query (*Query-Time Tax*)**: A ogni richiesta, l'LLM deve sintetizzare da zero frammenti disomogenei e non consolidati.
* **Assenza di memoria evolutiva**: Il database vettoriale è passivo; non rileva contraddizioni né consolida progressivamente la conoscenza.

**LLM Wiki** rovescia il paradigma: sposta l'onere computazionale e cognitivo **dalla fase di query alla fase di compilazione (ingestione)**.

| Caratteristica | RAG Tradizionale | LLM Wiki Desktop |
| :--- | :--- | :--- |
| **Rappresentazione Dati** | Vettori numerici opachi in Vector DB | File Markdown `.md` leggibili dall'uomo in file-system locale |
| **Sforzo Computazionale** | Concentrato alla query (alta latenza e costi) | Concentrato all'ingestione (conoscenza pre-compilata) |
| **Interazione Utente** | Sola lettura / Chatbot effimero | Bivalente: Utente e AI leggono e modificano le stesse note |
| **Dati Tabellari** | Pessimo (frammentazione di righe CSV o JSON) | Schede metadati + Kernel Python isolato (Jupyter-like) |
| **Struttura Relazionale** | Similarità semantica stimata (spesso rumorosa) | Grafo esplicito di `[[wikilink]]` bidirezionali |

---

## ✨ Funzionalità Chiave

- **📄 Ingestione Multimodale ad Alta Fedeltà**: Parsing di paper PDF, scansioni, immagini e diagrammi tecnici tramite `docling` e modelli Vision. Formule estratte rigorosamente in $\LaTeX$ ($inline$ e $$display$$).
- **📝 Conoscenza Atomica Compilata**: Decomposizione automatica delle fonti in note concettuali atomiche correlate tramite `[[wikilink]]` e provviste di metadati frontmatter standardizzati YAML.
- **🔒 Immutabilità dei Sorgenti (*Source Provenance*)**: La directory `sources/` è di sola lettura per l'AI. Ogni nota conserva il riferimento bibliografico immutabile alla fonte primaria.
- **📊 Data Science Sandbox**: Nessuna serializzazione selvaggia di dati tabellari nel contesto. Generazione ed esecuzione dinamica di script Python in un kernel Jupyter locale per calcolo di correlazioni, regressioni e rendering di grafici `matplotlib`/`seaborn`.
- **🌐 Visualizzatore di Grafo Interattivo**: Navigazione visuale 2D delle connessioni, raggruppamento semantico e colorazione differenziata per tipologia (`concept`, `entity`, `dataset`, `synthesis`).
- **🔍 Knowledge Linting Continuo**: Rilevamento automatico di link orfani, nodi isolati, cluster disconnessi e contraddizioni semantiche registrate in `_index/lint_report.md`.
- **📂 Obsidian & Local-First Native**: L'intero archivio è un normale vault Markdown su disco, apribile e modificabile liberamente con Obsidian, VS Code o qualsiasi editor di testo.

---

## 🗂 Topologia del Vault

Ogni knowledge base rispetta una struttura a cartelle deterministica:

```text
<vault_root>/
├── sources/               # IMMUTABILE (Read-Only per l'AI)
│   ├── papers/            # PDF, EPUB, TXT originali
│   ├── images/            # Schemi architetturali, scansioni, diagrammi
│   └── datasets/          # CSV, TSV, Parquet, database SQLite
├── wiki/                  # CONOSCENZA COMPILATA (Editabile da Utente e AI)
│   ├── concepts/          # Note atomiche su principi, teorie, algoritmi
│   ├── entities/          # Note su librerie, tool, modelli, persone, dataset
│   └── synthesis/         # Rassegne comparative, report, Maps of Content (MOC)
├── _index/                # INDICI E METADATI DEL GRAFO
│   ├── INDEX.md           # Master directory navigabile con abstract su riga singola
│   ├── graph.json         # Cache di adiacenza del grafo per rendering istantaneo
│   └── lint_report.md     # Audit semantico: link orfani, conflitti, discrepanze
├── scripts/               # RUNTIME COMPUTAZIONALE
│   ├── sandbox_runner.py  # Wrapper di esecuzione dinamica
│   └── generated/         # Script Python analitici generati dall'agente
└── CLAUDE.md              # Regole di scrittura e invarianti operative per agenti AI
```

---

## 🏗 Architettura di Sistema

L'applicazione adotta un'architettura ibrida Desktop + Sidecar Locale ad alte prestazioni:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   DESKTOP FRONTEND (Tauri 2.0 + Rust)                  │
│  ┌─────────────────────────┬───────────────────┬────────────────────┐  │
│  │ Tree View & Graph Panel │ TipTap MD Editor  │ Execution Console  │  │
│  │ (D3 / Force-Graph)      │ (KaTeX + WikiLink)│ (Streaming Logs)   │  │
│  └─────────────────────────┴───────────────────┴────────────────────┘  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ IPC / Localhost HTTP
┌───────────────────────────────────▼────────────────────────────────────┐
│                  BACKEND ENGINE (FastAPI Sidecar Process)              │
│  ┌─────────────────────────┬───────────────────┬────────────────────┐  │
│  │ Ingestion & Vision      │ LLM Orchestrator  │ Execution Sandbox  │  │
│  │ (Docling, Marker)       │ (Claude, Ollama)  │ (IPykernel/Jupyter)│  │
│  └─────────────────────────┴───────────────────┴────────────────────┘  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ I/O Diretto su File System
┌───────────────────────────────────▼────────────────────────────────────┐
│                         VAULT LOCALE (Markdown)                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠 Stack Tecnologico

- **Desktop Shell**: [Tauri v2](https://tauri.app/) (Rust) per footprint ridotto (<40MB RAM) e sicurezza file system.
- **Frontend UI**: React 18, TypeScript, Tailwind CSS, Lucide Icons.
- **Editor Markdown**: TipTap con estensioni personalizzate per:
  - Rendering matematico $\LaTeX$ in tempo reale tramite KaTeX.
  - Autocompletamento fuzzy dei collegamenti `[[wikilink]]` indicizzati su `_index/INDEX.md`.
- **Graph Visualization**: `@visx/network` / `react-force-graph-2d`.
- **Backend Core**: Python 3.11+, FastAPI, Pydantic v2, Uvicorn.
- **Parsing & Ingestion**: `docling`, `marker-pdf`, `polars`, `Pillow`.
- **Sandbox Computazionale**: `ipykernel` / `jupyter-client` con timeout controllato e cattura stream stdout/stderr/matplotlib.
- **Integrazione LLM**:
  - API Cloud: Anthropic Claude (Claude 3.5 Sonnet), OpenAI (GPT-4o).
  - Runtime Locali: [Ollama](https://ollama.ai/) / [vLLM](https://github.com/vllm-project/vllm) per inferenza offline (Qwen 2.5 Coder, Llama 3).

---

## 🚀 Installazione & Setup

### Prerequisiti
- [Rust](https://www.rust-lang.org/) (versione 1.75 o superiore)
- [Node.js](https://nodejs.org/) (versione 18 o superiore) & `pnpm`
- [Python](https://www.python.org/) (versione 3.11 o superiore) & [`uv`](https://github.com/astral-sh/uv) (consigliato per velocità)

### 1. Clonazione del Repository
```bash
git clone https://github.com/tuo-username/llm-wiki-desktop.git
cd llm-wiki-desktop
```

### 2. Configurazione del Backend (Sidecar)
```bash
cd src/backend
uv venv
source .venv/bin/activate  # Su Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
cp .env.example .env       # Configura le tue API key (ANTHROPIC_API_KEY, OPENAI_API_KEY, OLLAMA_BASE_URL)
```

### 3. Installazione Dipendenze Frontend
```bash
cd ../frontend
pnpm install
```

### 4. Avvio in Modalità Sviluppo
Dalla root del progetto, esegui il runner Tauri:
```bash
pnpm tauri dev
```

---

## ⚙️ Workflow Operativi

### Pipeline A: Ingestione e Compilazione (`IngestAndCompile`)
```bash
sources/papers/paper.pdf ──► Docling Parser ──► Estrazione Markdown grezzo
                                                         │
                                                         ▼
wiki/concepts/nuova_nota.md ◄── Agente Compilatore (LLM) ──► _index/INDEX.md
```
1. Trascina un PDF in `sources/papers/`.
2. Il parser estrae testo, gerarchie, tabelle e formule matematiche in $\LaTeX$.
3. L'agente confronta l'estratto con `_index/INDEX.md`, crea le pagine atomiche in `wiki/concepts/` e vi inserisce i collegamenti `[[...]]`.
4. Il master index e la mappa `_index/graph.json` vengono rigenerati.

#### Ingestione di documenti da engine OCR esterni (dots.mocr, DeepSeek-OCR-2, …)

I documenti che richiedono OCR (scansioni, fax, tabelle dense, grafici) possono
essere convertiti **al di fuori** dell'app con un VLM (dots.mocr,
DeepSeek-OCR-2, LlamaParse cloud, …) e importati qui come risultato:

1. **Pulsante «📁 Ingerisci cartella OCR»**: seleziona la cartella di output
   (es. `report.md` + `imgs/`). I file vengono salvati sotto `sources/`
   preservando la struttura; i riferimenti a immagini relative dei `.md`
   vengono riscritti verso `sources/images/`.
2. Le **tabelle Markdown** dei `.md` sono estratte come tabelle strutturate
   (stesso contratto dei PDF) e — come per ogni documento — esportate in
   `sources/datasets/` come `.tsv`, quindi **analizzabili nello Sandbox**
   con i template predefiniti.
3. Un **frontmatter YAML** opzionale nel `.md` documenta la provenienza
   (`source: contratto.pdf`, `engine: dots.mocr`, …) ed è preservato nei
   metadati del documento.
4. **Opzionale — engine nativo (`LLW_PDF_ENGINE`)**: un servizio OCR HTTP
   locale (VLM su GPU, `tools/ocr_http_server.py` di riferimento) può
   essere puntato via `LLW_OCR_HTTP_URL`. Con `auto`, i PDF con layer
   testuale rado (scansioni) vengono instradati al VLM, mentre i PDF
   born-digital restano sul motore built-in (veloce, zero AI).

### Pipeline B: Calcolo e Data Science Sandboxed
1. Rilascia un dataset in `sources/datasets/vendite.csv`.
2. L'agente profila le colonne via `polars` e scrive la scheda metadati in `wiki/entities/vendite.md`.
3. Chiedi: *"Calcola la matrice di correlazione tra le variabili X e Y e visualizza la retta di regressione."*
4. L'agente genera uno script in `scripts/generated/task_01.py`, lo esegue nel kernel Python, salva il grafico in `sources/images/generated/plot_01.png` e compila il report formale in `wiki/synthesis/analisi_vendite.md`.

---

## 🤖 Integrazione Agenti: `SKILL.md`

Il progetto include uno standard formale aperto per agenti di codifica autonomi conforme alle specifiche **Agent Skills**:

- **Percorso specifica**: [`skills/llm-wiki-builder/SKILL.md`](skills/llm-wiki-builder/SKILL.md)
- **Compatibilità**: [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code), [Cursor Composer](https://cursor.sh/), [Windsurf Cascade](https://codeium.com/windsurf), [Aider](https://aider.chat/).

Per delegare miglioramenti o manutenzione all'agente di sviluppo:
```bash
claude "Leggi skills/llm-wiki-builder/SKILL.md ed esegui la suite di test di conformità sul parser PDF."
```

---

## 🗺 Roadmap

- [x] Ingestione PDF multimodale ad alta risoluzione (Docling).
- [x] Generazione deterministica note atomiche con frontmatter YAML e $\LaTeX$.
- [x] Sandbox isolata con kernel Jupyter per esecuzione script Python.
- [x] Master Index automatico e graph cache (`graph.json`).
- [ ] Supporto a modelli locali con quantizzazione GGUF embedded (senza dipendenze esterne).
- [ ] Sincronizzazione P2P crittografata end-to-end del Vault tra dispositivi.
- [ ] Plugin ufficiale per Obsidian per navigazione trasparente del compilatore.

---

## 📄 Licenza

Distribuito sotto Licenza MIT. Consulta il file [`LICENSE`](LICENSE) per ulteriori dettagli.

---

<div align="center">
  <sub>Sviluppato con dedizione secondo i principi architetturali della <b>Compiled Knowledge</b>.</sub>
</div>
