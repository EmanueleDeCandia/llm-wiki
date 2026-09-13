// LLM Wiki Desktop — shell Tauri (scaffold per il packaging successivo).
//
// L'applicazione è già completa in modalità Web + sidecar FastAPI:
// questa finestra carica la dev-server Vite in sviluppo e la build `dist/`
// in produzione. Il sidecar Python (src/backend) viene avviato separatamente
// (`python run.py`, porta 8100) oppure, in un passo successivo, tramite
// tauri-plugin-shell come processo figlio gestito da Tauri.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .run(tauri::generate_context!())
        .expect("errore avvio Tauri");
}
