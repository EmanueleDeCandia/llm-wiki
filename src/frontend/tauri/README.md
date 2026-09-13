# Shell Tauri (packaging desktop — fase successiva)

Scaffold pronto per l'imballaggio desktop secondo la Skill §5.1
(`Tauri (Rust)`). L'applicazione funziona già oggi in modalità
**Web + sidecar** (Vite su 5173 → FastAPI su 8100).

## Requisiti

- Rust ≥ 1.75 e le dipendenze di sistema Tauri v2 (su Linux: `webkit2gtk-4.1`, `libayatana-appindicator3`, …)
- Node 18+ e le dipendenze del frontend

## Avvio

```bash
# dal repo root, con pnpm install già fatto in src/frontend
pnpm tauri dev      # sviluppo
pnpm tauri build    # bundle desktop (dist desktop in ../dist)
```

## Integrazione sidecar (passo successivo previsto)

Il backend FastAPI è un sidecar process: per gestirlo da Tauri basterà
aggiungere a `tauri/src/main.rs` un comando che spawn
`python src/backend/run.py` (API_PORT=8100) al `setup` e lo termina con
la finestra, usando `tauri-plugin-shell` già dichiarato in `Cargo.toml`.
