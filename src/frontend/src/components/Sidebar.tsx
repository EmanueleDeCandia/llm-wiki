import { useRef, useState } from 'react';
import { useStore } from '../store';
import { FileTree } from './FileTree';
import { GraphView, TYPE_LABELS } from './GraphView';
import { api } from '../api/client';
import type { GraphNode } from '../types';

export function Sidebar({
  onNavigate,
  onRefresh,
}: {
  onNavigate: (path: string, title: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const tree = useStore((s) => s.tree);
  const graph = useStore((s) => s.graph);
  const notes = useStore((s) => s.notes);
  const [tab, setTab] = useState<'files' | 'graph'>('files');
  const fileInput = useRef<HTMLInputElement>(null);
  const [ingesting, setIngesting] = useState(false);

  const handleIngest = async (file: File) => {
    setIngesting(true);
    try {
      const res = await api.ingest(file);
      useStore.getState().set({
        statusMessage: `Ingerito ${res.source_path} → ${res.notes_created.length} note [${res.parser}/${res.compiler}]`,
      });
      await onRefresh();
    } catch (e) {
      useStore.getState().set({ statusMessage: `Ingestione fallita: ${String(e)}` });
    } finally {
      setIngesting(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  const openGraphNode = (n: GraphNode) => {
    if (n.type === 'source') {
      useStore.getState().set({ statusMessage: `Sorgente immutabile: ${n.id}` });
      return;
    }
    onNavigate(n.id, n.title);
  };

  const handleDeleteFile = async (path: string) => {
    if (!window.confirm(`Eliminare il file:\n${path}\n?\n\nLe sorgenti in sources/ (fuori da generated) non sono eliminabili.`)) {
      return;
    }
    try {
      await api.deleteFile(path);
      useStore.getState().set({ statusMessage: `Eliminato: ${path}` });
      await onRefresh();
    } catch (e) {
      useStore.getState().set({ statusMessage: `Eliminazione fallita: ${String(e)}` });
    }
  };

  return (
    <aside className="w-72 shrink-0 flex flex-col border-r border-ink-700 bg-ink-900">
      <div className="flex items-center gap-1 p-2 border-b border-ink-700">
        <button
          onClick={() => setTab('files')}
          className={`flex-1 text-[11.5px] py-1.5 rounded-md ${
            tab === 'files' ? 'bg-ink-700 text-slate-100' : 'text-slate-400 hover:bg-ink-800'
          }`}
        >
          📂 File
        </button>
        <button
          onClick={() => setTab('graph')}
          className={`flex-1 text-[11.5px] py-1.5 rounded-md ${
            tab === 'graph' ? 'bg-ink-700 text-slate-100' : 'text-slate-400 hover:bg-ink-800'
          }`}
        >
          🕸 Grafo{graph ? ` (${graph.node_count})` : ''}
        </button>
      </div>

      {tab === 'files' && (
        <>
          <div className="p-2 border-b border-ink-700">
            <input
              ref={fileInput}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                for (const f of Array.from(e.target.files || [])) handleIngest(f);
              }}
            />
            <button
              onClick={() => fileInput.current?.click()}
              disabled={ingesting}
              className="w-full text-[12px] py-2 rounded-lg bg-sky-600/90 hover:bg-sky-500 disabled:opacity-50 text-white font-semibold"
            >
              {ingesting ? 'Ingestione in corso…' : '⬆ Ingerisci file (PDF · img · CSV…)'}
            </button>
            <div className="text-[10px] text-slate-500 mt-1 px-1">
              → sources/ è immutabile: le note compilate finiscono in wiki/
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            <FileTree
            root={tree}
            onOpenFile={(p) => onNavigate(p, '')}
            onDeleteFile={(p) => void handleDeleteFile(p)}
          />
          </div>
        </>
      )}

      {tab === 'graph' && (
        <div className="flex-1 min-h-0 relative">
          {graph ? (
            <GraphView graph={graph} onNodeClick={openGraphNode} height="100%" />
          ) : (
            <div className="p-4 text-[12px] text-slate-500">Nessun grafo: apri un vault.</div>
          )}
          <div className="absolute bottom-2 right-2 bg-ink-900/90 border border-ink-700 rounded px-2 py-1 text-[10px] text-slate-400">
            {notes.length} note · colori: {Object.values(TYPE_LABELS).slice(0, 4).join(' · ')}
          </div>
        </div>
      )}
    </aside>
  );
}
