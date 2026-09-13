# CLAUDE.md — Regole operative interne al vault

Questo file definisce gli invarianti vincolanti per **ogni** agente secondario
(Utente, LLM, script) che legge o scrive in questo archivio.

## Invarianti (non negoziabili)

1. **`sources/` è immutabile**: nessun modello o sottoprocesso AI può
   modificare, rinominare o sovrascrivere file in `sources/`.
   Unica eccezione: `sources/images/generated/`, cartella di output gestita
   dall'engine per le figure delle esecuzioni sandbox.
2. **Provenienza**: ogni nota in `wiki/` dichiara nel frontmatter YAML il
   file originale esatto: `sources: ["[[sources/papers/documento.pdf]]"]`.
3. **Isolamento dei dati tabellari**: mai serializzare dataset estesi in
   tabelle Markdown. Per CSV/Parquet/SQLite esiste solo la scheda metadati
   in `wiki/entities/`; calcoli e grafici si eseguono via script Python nel
   sandbox (`/api/v1/sandbox/run`).
4. **Notazione matematica**: esclusivamente LaTeX standard (`$inline$`,
   `$$display$$`). Mai simboli matematici Unicode.
5. **Collegamenti**: ogni riferimento a un'altra nota usa `[[Wikilink]]`
   con il titolo esatto o il percorso nel vault.

## Topologia

```
sources/           (immutabile)   papers/, images/, datasets/
wiki/concepts/     note atomiche su principi e teorie
wiki/entities/     strumenti, librerie, persone, modelli, dataset
wiki/synthesis/    report aggregati, rassegne, MOC
_index/            INDEX.md, graph.json, lint_report.md (generati dall'engine)
scripts/generated/ script Python persistenti prodotti dal sandbox
```

## Schema frontmatter (obbligatorio)

```yaml
---
title: "Identificatore Univoco del Concetto"
type: concept        # concept | entity | dataset | synthesis
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources:
  - "[[sources/papers/documento_originale.pdf]]"
aliases:
  - "Sinonimo"
tags:
  - dominio/sotto-dominio
relations:
  prerequisites: []
  related: []
  conflicts_with: []
---
```

## Struttura del corpo (obbligatoria)

1. `# {Title}`
2. `## Sintesi Esecutiva` — max 3 frasi ad alta densità
3. `## Formalizzazione & Dettagli` — trattazione con LaTeX
4. `## Relazioni nel Grafo` — elenco `[[Nome Pagina]]`
5. `## Discrepanze & Limiti` — divergenze tra fonti e limiti noti
