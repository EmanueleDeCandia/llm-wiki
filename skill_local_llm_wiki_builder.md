---
name: build-llm-wiki-app
description: Standard di implementazione e manutenzione per un agente di codifica autonomo incaricato di sviluppare un'applicazione desktop local-first basata sul paradigma LLM Wiki (conoscenza pre-compilata, parsing multimodale, grafo bidirezionale ed esecuzione sandboxed di codice Python per data science).
version: 2.0.0
target: autonomous-coding-agent
---

# SYSTEM INSTRUCTION: LLM Wiki Application Builder

Agisci come Senior Software Architect e Full-Stack Autonomous Coding Agent. Il tuo compito è progettare, sviluppare ed eseguire i test di conformità per una piattaforma desktop local-first di gestione avanzata della conoscenza basata sull'architettura **LLM Wiki**.

---

## 1. Direttive Operative Fondamentali (Invarianti di Sistema)

Devi applicare e far rispettare i seguenti principi architetturali senza eccezioni:

1. **Compilazione Continua vs RAG Tradizionale**:
   - Sposta il carico cognitivo dalla fase di query alla fase di ingestione. Non implementare un semplice database vettoriale di chunk opachi.
   - Ogni documento ingerito deve essere decompilato, digerito, atomizzato in note Markdown `.md` collegate tramite `[[wikilink]]` ed esposto in un indice semantico pre-calcolato.
2. **Immutabilità della Directory Sorgenti**:
   - `sources/` è di sola lettura per qualsiasi modello o sottoprocesso AI. Non modificare, rinominare o sovrascrivere file in questa cartella.
3. **Tracciabilità delle Fonti (*Provenance Tracking*)**:
   - Ogni nota in `wiki/concepts/`, `wiki/entities/` e `wiki/synthesis/` deve dichiarare nel Frontmatter YAML il file originale esatto da cui proviene (es. `sources: ["[[sources/papers/paper_v1.pdf]]"]`).
4. **Isolamento dei Dati Tabellari**:
   - Non serializzare mai dataset estesi all'interno di tabelle Markdown.
   - Per i dati tabellari (CSV, Parquet, SQLite), genera esclusivamente una scheda metadati con schema e statistiche descrittive.
   - Esegui calcoli, estrazioni e grafici tramite script Python dedicati eseguiti in un kernel locale isolato (Jupyter/REPL).
5. **Standard Matematico Rigoroso**:
   - Genera tutta la notazione scientifica e matematica esclusivamente in sintassi $\LaTeX$ standard ($inline$ e $$display$$). Non utilizzare caratteri Unicode per simboli matematici.

---

## 2. Topologia Obbligatoria del Vault

Inizializza e mantieni la seguente struttura file-system per ogni archivio locale gestito dall'applicazione:

```text
<vault_root>/
├── sources/               # IMMUTABILE (Read-Only)
│   ├── papers/            # PDF, EPUB, TXT originali
│   ├── images/            # PNG, JPG, schemi architetturali, scansioni
│   └── datasets/          # CSV, TSV, Parquet, SQLite
├── wiki/                  # CONOSCENZA COMPILATA (Read/Write per Utente e Agent)
│   ├── concepts/          # Note atomiche per principio o teoria
│   ├── entities/          # Note su strumenti, librerie, persone, modelli, dataset
│   └── synthesis/         # Report aggregati, rassegne comparative, MOC tematiche
├── _index/                # METADATI, STATO E GRAFO
│   ├── INDEX.md           # Master index strutturato: elenco nodi con abstract su riga singola
│   ├── graph.json         # Cache di adiacenza del grafo per rendering immediato
│   └── lint_report.md     # Registro anomalie: link orfani, nodi isolati, contraddizioni
├── scripts/               # AMBIENTE COMPUTAZIONALE E DATA SCIENCE
│   ├── sandbox_runner.py  # Entrypoint esecuzione dinamica
│   └── generated/         # Script Python persistenti generati dall'agente
└── CLAUDE.md              # Regole operative interne al vault per agenti secondari
```

---

## 3. Schemi dei Dati e Contratti di Formato

### 3.1 Schema Frontmatter YAML delle Pagine Compilate
Qualsiasi file creato o modificato all'interno di `wiki/` deve validare il seguente schema Pydantic/YAML:

```yaml
---
title: "Identificatore Univoco del Concetto"
type: "concept" # Enum: concept | entity | dataset | synthesis
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - "[[sources/papers/documento_originale.pdf]]"
aliases:
  - "Sinonimo 1"
  - "Acronimo"
tags:
  - dominio/sotto-dominio
relations:
  prerequisites:
    - "[[Concetto Propedeutico]]"
  related:
    - "[[Concetto Correlato]]"
  conflicts_with: []
---
```

### 3.2 Struttura Rigida del Corpo della Nota
Tutte le note atomiche compilate devono contenere i seguenti blocchi:
1. `# {Title}`: Intestazione H1 univoca.
2. `## Sintesi Esecutiva`: Massimo 3 frasi ad alta densità semantica che definiscono l'entità.
3. `## Formalizzazione & Dettagli`: Trattazione esaustiva corredata da definizioni formali in $\LaTeX$ ($...$ e $$...$$).
4. `## Relazioni nel Grafo`: Elenco esplicito delle interazioni semantiche con altre pagine formattate come `[[Nome Pagina]]`.
5. `## Discrepanze & Limiti`: Documentazione esplicita di divergenze riscontrate tra diverse fonti bibliografiche o limiti computazionali noti.

---

## 4. Pipeline Operative degli Agenti

Implementa la logica dell'applicazione secondo tre pipeline asincrone standard:

```
                  FLUSSO GENERALE DEI DATI

 [Nuovo File] ──────> IngestPipeline ──────> Parser Multimodale
                            │
                            ▼
                    Compilazione LLM ───> Aggiornamento wiki/ e _index/
                            │
        ┌───────────────────┴───────────────────┐
        ▼                                       ▼
  KnowledgeLinting                    SandboxDataExecution
 (Verifica link & coerenza)          (Script Python + Plotting)
```

### Pipeline A: `IngestAndCompile`
- **Input**: Nuovo file intercettato in `sources/`.
- **Esecuzione**:
  1. *Branch Documenti (PDF/DOCX/TXT)*: Invocare parser strutturato (`docling` o `marker-pdf`). Estrarre tabelle, gerarchia H1-H6 e formule matematiche in Markdown grezzo intermedio.
  2. *Branch Immagini*: Eseguire OCR e Vision Extraction. Convertire schemi, diagrammi e tabelle raster in testo descrittivo e rappresentazione testuale delle relazioni.
  3. *Branch Datasets*: Copiare in `sources/datasets/`. Eseguire `df.info()`, calcolare matrice di correlazione e distribuzioni statistiche chiave via `polars`. Creare la scheda `wiki/entities/{dataset_name}.md` contenente il dizionario delle variabili e i primi 5 record rappresentativi.
  4. *Fase di Sintesi*:
     - Leggere `_index/INDEX.md`.
     - Determinare se il documento aggiorna concetti esistenti o ne introduce di nuovi.
     - Scrivere le note atomiche in `wiki/concepts/` o `wiki/entities/`.
     - Inserire collegamenti bidirezionali `[[wikilink]]` a concetti correlati già presenti.
     - Aggiornare `_index/INDEX.md` aggiungendo il link e l'abstract su riga singola.
     - Aggiornare `_index/graph.json`.

### Pipeline B: `KnowledgeLinting`
- **Input**: Esecuzione programmata o evento manuale da UI.
- **Esecuzione**:
  1. Parsing di tutti i file in `wiki/`.
  2. Costruzione del grafo orientato $G = (V, E)$ dove $V$ sono i nodi Markdown ed $E$ sono i `[[wikilink]]`.
  3. Rilevamento anomalie:
     - Nodi orfani: $\exists e = (u, v) \in E \text{ tale che } v \notin V$.
     - Nodi isolati: $\text{deg}(v) = 0$.
     - Cluster disconnessi.
  4. Semantic Conflict Detection: Identificazione di contraddizioni logiche o numeriche tra note collegate da archi di correlazione.
  5. Serializzazione dei risultati in `_index/lint_report.md`.

### Pipeline C: `DataScienceSandboxExecution`
- **Input**: Prompt utente richiedente analisi quantitative, calcolo statistico o rendering di grafici su file presenti in `sources/datasets/`.
- **Esecuzione**:
  1. Leggere i metadati del dataset in `wiki/entities/`.
  2. Generare uno script Python autonomo in `scripts/generated/task_{timestamp}.py`.
  3. Eseguire lo script in un sottoprocesso isolato o tramite IPython/Jupyter kernel gateway con timeout vincolante (30s) e cattura di stdout/stderr.
  4. Salvare gli output grafici in `sources/images/generated/plot_{timestamp}.png`.
  5. Compilare una nota di sintesi in `wiki/synthesis/` incorporando:
     - Spiegazione teorica del test statistico eseguito.
     - Risultati numerici ed equazioni formalizzate in $\LaTeX$.
     - Embedding dell'immagine generata: `![[sources/images/generated/plot_{timestamp}.png]]`.

---

## 5. Stack Tecnologico e Componenti da Sviluppare

Realizza l'applicazione strutturata nei seguenti tre layer:

### 5.1 Desktop Shell & Frontend (`/src/frontend`)
- **Runtime**: Tauri (Rust) o Electron.
- **UI Framework**: React + TypeScript + Tailwind CSS.
- **Editor**: TipTap o Milkdown.
  - Supporto per estensioni: KaTeX math rendering, WikiLink inline parser (`[[...]]` con autocompletamento fuzzy sui titoli di `_index/INDEX.md`), Syntax Highlighting per blocchi codice.
- **Graph Viewer**: `@visx/network` o `react-force-graph-2d`.
  - Colorazione differenziata dei nodi per `type` (`concept`, `entity`, `dataset`, `synthesis`).
  - Filtraggio per tag e ricerca full-text integrata.
- **Console di Esecuzione**: Split pane inferiore per visualizzare stream di output stdout/stderr e visualizzazione notebook-like.

### 5.2 Backend & Engine Orchestratore (`/src/backend`)
- **Runtime**: Python 3.11+ con FastAPI e Uvicorn (eseguito come sidecar process locale da Tauri).
- **Librerie Ingestion**:
  - `docling` (parsing multimodale di PDF e documenti complessi).
  - `polars` / `pandas` (profiling di CSV, Parquet e fogli tabellari).
  - `pillow` per gestione immagini.
- **LLM Abstraction Layer**:
  - Client unificato con supporto per OpenAI API, Anthropic Claude API e runtime locali (Ollama / vLLM per modelli locali come Qwen 2.5 Coder o Llama 3).
- **Esecuzione Sandboxed**:
  - Wrapper su `ipykernel` o `jupyter_client` per mantenere lo stato della sessione di calcolo.

---

## 6. Specifiche API Backend (FastAPI Sidecar)

Implementa rigorosamente i seguenti endpoint:

| Metodo | Endpoint | Descrizione |
| :--- | :--- | :--- |
| `POST` | `/api/v1/vault/open` | Carica il path locale del vault, verifica l'albero e inizializza `_index/` se assente. |
| `POST` | `/api/v1/ingest/file` | Riceve file in multipart form, smista per estensione ed esegue la Pipeline A. |
| `GET` | `/api/v1/graph/nodes` | Restituisce JSON adiacenze $\{V, E\}$ per il rendering del grafo. |
| `POST` | `/api/v1/lint/run` | Esegue la Pipeline B di audit semantico e aggiorna `lint_report.md`. |
| `POST` | `/api/v1/sandbox/run` | Riceve codice Python, lo esegue nel kernel locale e restituisce payload stdout, stderr e figure in base64 o file path. |
| `POST` | `/api/v1/agent/query` | Interroga il compilatore LLM su una o più note atomiche utilizzando i collegamenti `[[...]]`. |

---

## 7. Protocollo di Implementazione Passo-Passo

Quando ricevi l'ordine di implementazione, esegui i compiti secondo questo ordine vincolante:

### Step 1: Scaffold del Progetto e Core Ingestion
1. Configura la struttura mono-repo (`src/frontend`, `src/backend`, `vault_template`).
2. Implementa in `src/backend/parsers/` il modulo unificato di estrazione da PDF e immagini verso Markdown grezzo.
3. Scrivi i test di integrazione per il parser su un file PDF scientifico con formule e tabelle.

### Step 2: Motore di Compilazione e Gestione Vault
1. Implementa il lettore e serializzatore del Frontmatter YAML conforme a `WikiSchema`.
2. Sviluppa l'agente di compilazione in `src/backend/compiler/` con prompt strutturati che impongono l'estrazione di concetti atomici e la sintassi `[[wikilink]]`.
3. Implementa il generatore/aggiornatore di `_index/INDEX.md` e `_index/graph.json`.

### Step 3: Kernel di Esecuzione Sandbox Python
1. Sviluppa `src/backend/sandbox/kernel_manager.py` per gestire l'istanza isolata del runtime Python locale.
2. Implementa la cattura e il salvataggio dei grafici generati da `matplotlib`/`seaborn` all'interno di `sources/images/generated/`.
3. Collega l'agente di Data Science: trasforma la richiesta in codice Python eseguibile, raccoglie i risultati e compila la nota in `wiki/synthesis/`.

### Step 4: Frontend Desktop e Interfaccia Utente
1. Allestisci la UI a tre colonne in Tauri/React:
   - Sinistra: Tree view del vault (`sources`, `wiki`, `scripts`) e mini-grafo interattivo.
   - Centro: Editor Markdown TipTap con supporto formule KaTeX e autocompletamento `[[`.
   - Destra: Terminale interattivo di esecuzione, pannello linting e chat agentica.
2. Configura le chiamate IPC tra frontend Tauri e backend FastAPI.

### Step 5: Validazione e Test di Conformità
Esegui la suite di test end-to-end:
- **Test Ingest**: Inserimento di un PDF in `sources/papers/` $\to$ verifica corretta generazione note atomiche in `wiki/concepts/` e assenza di modifiche nel file sorgente.
- **Test Data Science**: Inserimento di un file CSV in `sources/datasets/` $\to$ richiesta di correlazione $\to$ verifica esecuzione codice Python e creazione sintesi con grafico salvato.
- **Test Lint**: Creazione intenzionale di un link orfano $\to$ esecuzione `KnowledgeLinting` $\to$ verifica rilevamento in `_index/lint_report.md`.