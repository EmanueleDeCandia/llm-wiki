import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client';
import { ConsolePane } from './components/ConsolePane';
import { EditorPane } from './components/EditorPane';
import { LintPanel } from './components/LintPanel';
import { QueryPanel } from './components/QueryPanel';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { VaultOpenScreen } from './components/VaultOpen';
import { useStore } from './store';

const IMAGE_EXT = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'];

export default function App() {
  const online = useStore((s) => s.online);
  const health = useStore((s) => s.health);
  const vaultOpen = useStore((s) => s.vaultOpen);
  const filePreview = useStore((s) => s.filePreview);
  const set = useStore((s) => s.set);
  const [rightTab, setRightTab] = useState<'console' | 'lint' | 'query'>('console');

  const refreshData = useCallback(async () => {
    try {
      const [tree, notes, graph] = await Promise.all([api.tree(), api.notes(), api.graph()]);
      set({ tree, notes, graph });
    } catch (e) {
      set({ statusMessage: `Refresh: ${String(e)}` });
    }
  }, [set]);

  // health + stato sidecar
  useEffect(() => {
    const poll = async () => {
      try {
        const h = await api.health();
        set({ health: h, online: true, vaultOpen: h.vault_open, statusMessage: null });
        if (h.vault_open) void refreshData();
      } catch {
        set({ online: false, health: null, vaultOpen: false });
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, [set, refreshData]);

  const openVault = async (root: string) => {
    try {
      const h = await api.health();
      set({ health: h, vaultOpen: h.vault_open });
      await refreshData();
      set({ statusMessage: `Vault aperto: ${root}` });
    } catch (e) {
      set({ statusMessage: String(e) });
    }
  };

  const navigate = useCallback(
    async (path: string, _title?: string) => {
      try {
        if (path.startsWith('wiki/') && path.endsWith('.md')) {
          const note = await api.readNote(path);
          useStore.getState().openNote(path, note.raw);
          set({ filePreview: null });
        } else {
          const ext = path.split('.').pop()?.toLowerCase() || '';
          if (IMAGE_EXT.includes(ext)) {
            set({ filePreview: { path, url: api.fileUrl(path) } });
          } else {
            const res = await fetch(api.fileUrl(path));
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            set({ filePreview: { path, text: await res.text() } });
          }
        }
      } catch (e) {
        set({ statusMessage: `Apertura ${path}: ${String(e)}` });
      }
    },
    [set],
  );

  const onWikilink = useCallback(
    (target: string) => {
      const notes = useStore.getState().notes;
      const t = target.trim().toLowerCase();
      const byTitle = notes.find((n) => n.title.toLowerCase() === t);
      const bySlug = notes.find((n) => n.id.split('/').pop()?.replace('.md', '') === t.replace(/\.md$/, ''));
      const found = byTitle || bySlug;
      if (found) {
        void navigate(found.id, found.title);
      } else {
        set({ statusMessage: `Link orfano: [[${t}]] non presente nell'indice` });
      }
    },
    [navigate, set],
  );

  if (!online) {
    return (
      <div className="h-full flex items-center justify-center text-slate-400 text-[13px]">
        <div className="text-center">
          <div className="text-3xl mb-3 animate-pulse">📡</div>
        Connessione al sidecar FastAPI (http://127.0.0.1:8100)…
          <div className="text-[11px] text-slate-600 mt-2">
            Avvio: cd src/backend &amp;&amp; python run.py
          </div>
        </div>
      </div>
    );
  }

  if (!vaultOpen) {
    return <VaultOpenScreen onOpen={openVault} />;
  }

  return (
    <div className="h-full flex flex-col bg-ink-950 text-slate-200">
      <TopBar
        health={health}
        onRefresh={refreshData}
        onRebuildIndex={async () => {
          await api.indexRebuild();
          await refreshData();
          set({ statusMessage: 'Indice e grafo rigenerati' });
        }}
        onLint={async () => {
          setRightTab('lint');
          set({ lintRunning: true });
          try {
            const res = await api.lintRun();
            set({ lint: res });
          } catch (e) {
            set({ statusMessage: String(e) });
          } finally {
            set({ lintRunning: false });
          }
        }}
      />

      <div className="flex-1 min-h-0 flex">
        {/* colonna sinistra: file + grafo */}
        <Sidebar onNavigate={(p, t) => void navigate(p, t)} onRefresh={refreshData} />

        {/* colonna centrale: editor + anteprima file */}
        <main className="flex-1 min-w-0 bg-ink-850">
          {filePreview ? (
            <FilePreviewView
              path={filePreview.path}
              url={filePreview.url}
              text={filePreview.text}
              onClose={() => set({ filePreview: null })}
            />
          ) : (
            <EditorPane onWikilink={onWikilink} />
          )}
        </main>

        {/* colonna destra: console / lint / query */}
        <aside className="w-[400px] shrink-0 flex flex-col border-l border-ink-700 bg-ink-900">
          <div className="flex items-center gap-1 p-2 border-b border-ink-700">
            {(
              [
                ['console', '⌨ Sandbox'],
                ['lint', '🧪 Lint'],
                ['query', '💬 Query'],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                onClick={() => setRightTab(k)}
                className={`flex-1 text-[11.5px] py-1.5 rounded-md ${
                  rightTab === k ? 'bg-ink-700 text-slate-100' : 'text-slate-400 hover:bg-ink-800'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex-1 min-h-0">
            {rightTab === 'console' && <ConsolePane />}
            {rightTab === 'lint' && <LintPanel />}
            {rightTab === 'query' && <QueryPanel onOpenNote={(p, t) => void navigate(p, t)} />}
          </div>
        </aside>
      </div>
    </div>
  );
}

function FilePreviewView({
  path,
  url,
  text,
  onClose,
}: {
  path: string;
  url?: string;
  text?: string;
  onClose: () => void;
}) {
  return (
    <div className="h-full flex flex-col">
      <div className="h-9 flex items-center gap-3 px-3 border-b border-ink-700 bg-ink-900">
        <span className="text-[12px] text-slate-300 truncate font-mono">{path}</span>
        <span className="text-[10px] text-amber-300 border border-amber-500/40 rounded px-1.5">
          sorgente · read-only
        </span>
        <div className="flex-1" />
        <button onClick={onClose} className="text-[12px] text-slate-500 hover:text-slate-200">
          ✕ chiudi
        </button>
      </div>
      <div className="flex-1 overflow-auto p-4 bg-ink-950">
        {url ? (
          <img src={url} alt={path} className="max-w-full rounded-lg border border-ink-700 mx-auto" />
        ) : (
          <pre className="font-mono text-[12px] text-slate-300 whitespace-pre-wrap">{text}</pre>
        )}
      </div>
    </div>
  );
}
