import { useMemo, useRef, useState } from 'react';
import { api } from '../api/client';
import { MathPreview } from '../lib/markdown';
import { useStore } from '../store';
import type { NoteSummary } from '../types';

/** Autocompletamento fuzzy per i wikilink `[[...]]` sui titoli indicizzati. */
function useWikilinkAutocomplete() {
  const notes = useStore((s) => s.notes);
  const [popup, setPopup] = useState<{ query: string; start: number; pos: { x: number; y: number } } | null>(null);
  const [selected, setSelected] = useState(0);

  const items = useMemo(() => {
    if (!popup) return [];
    const q = popup.query.toLowerCase();
    const all: NoteSummary[] = notes;
    if (!q) return all.slice(0, 8);
    return all
      .filter((n) => {
        const hay = `${n.title} ${n.id} ${n.aliases.join(' ')}`.toLowerCase();
        // fuzzy: sottosequenza
        let i = 0;
        for (const ch of hay) if (ch === q[i]) i++;
        return i >= Math.min(q.length, 4);
      })
      .slice(0, 8);
  }, [popup, notes]);

  return { popup, items, selected, setSelected, setPopup };
}

export function EditorPane({ onWikilink }: { onWikilink: (target: string) => void }) {
  const openNotes = useStore((s) => s.openNotes);
  const activeNote = useStore((s) => s.activeNote);
  const { popup, items, selected, setSelected, setPopup } = useWikilinkAutocomplete();
  const [mode, setMode] = useState<'split' | 'edit' | 'preview'>('split');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const note = openNotes.find((n) => n.path === activeNote) || null;

  if (!note) {
    return (
      <div className="h-full flex items-center justify-center text-slate-500 text-[13px]">
        <div className="text-center">
          <div className="text-4xl mb-3">📝</div>
          Apri una nota da <code className="text-emerald-300">wiki/</code> oppure da un wikilink.
          <div className="text-[11px] mt-2 text-slate-600">
            Editor: frontmatter YAML + blocchi §3.2 · LaTeX KaTeX · autocompletamento [[wikilink]]
          </div>
        </div>
      </div>
    );
  }

  const detectWikilink = (value: string, caret: number) => {
    const before = value.slice(0, caret);
    const m = before.match(/\[\[([^\[\]]*)$/);
    if (m) {
      const el = taRef.current;
      const rect = el?.getBoundingClientRect();
      setPopup({
        query: m[1],
        start: caret - m[1].length - 2,
        pos: rect ? { x: 20, y: rect.height - 40 } : { x: 0, y: 0 },
      });
      setSelected(0);
    } else {
      setPopup(null);
    }
  };

  const applyWikilink = (title: string) => {
    if (!popup) return;
    const ta = taRef.current;
    if (!ta) return;
    const value = ta.value;
    const caret = ta.selectionStart;
    const next = value.slice(0, popup.start) + `[[${title}]]` + value.slice(caret);
    useStore.getState().noteContent(note.path, next);
    setPopup(null);
    requestAnimationFrame(() => {
      ta.focus();
      const pos = popup.start + title.length + 4;
      ta.setSelectionRange(pos, pos);
    });
  };

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await api.saveNote(note.path, note.content);
      useStore.getState().markSaved(note.path, note.content);
      useStore.getState().set({ statusMessage: `Salvata ${note.path}` });
    } catch (e) {
      setSaveError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* tab note aperte */}
      <div className="flex items-center gap-1 px-2 pt-2 overflow-x-auto shrink-0">
        {openNotes.map((n) => (
          <button
            key={n.path}
            onClick={() => useStore.getState().set({ activeNote: n.path })}
            className={`group flex items-center gap-1.5 text-[11.5px] px-3 py-1.5 rounded-t-lg border border-b-0 ${
              n.path === activeNote
                ? 'bg-ink-850 border-ink-700 text-slate-100'
                : 'bg-transparent border-transparent text-slate-500 hover:bg-ink-800'
            }`}
          >
            {n.dirty ? '●' : '○'} {n.path.split('/').pop()}
            <span
              className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-rose-400"
              onClick={(e) => {
                e.stopPropagation();
                useStore.getState().closeNote(n.path);
              }}
            >
              ✕
            </span>
          </button>
        ))}
        <div className="flex-1" />
        <div className="flex items-center gap-1 pb-1">
          {(['split', 'edit', 'preview'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`text-[10.5px] px-2 py-1 rounded ${
                mode === m ? 'bg-ink-700 text-slate-100' : 'text-slate-500 hover:bg-ink-800'
              }`}
            >
              {m === 'split' ? '◧' : m === 'edit' ? '✎' : '👁'}
            </button>
          ))}
          <button
            onClick={save}
            disabled={saving}
            className="text-[11px] px-3 py-1 rounded-md bg-emerald-600/80 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold"
          >
            {saving ? '…' : '💾 Salva'}
          </button>
        </div>
      </div>

      {/* corpo */}
      <div className="flex-1 min-h-0 flex border-t border-ink-700">
        {mode !== 'preview' && (
          <div className={`relative flex-1 min-w-0 ${mode === 'split' ? 'border-r border-ink-700' : ''}`}>
            <textarea
              ref={taRef}
              className="editor-area"
              value={note.content}
              spellCheck={false}
              onChange={(e) => {
                useStore.getState().noteContent(note.path, e.target.value);
                detectWikilink(e.target.value, e.target.selectionStart);
              }}
              onKeyDown={(e) => {
                if (popup && items.length) {
                  if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    setSelected((selected + 1) % items.length);
                  } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    setSelected((selected - 1 + items.length) % items.length);
                  } else if (e.key === 'Enter' || e.key === 'Tab') {
                    e.preventDefault();
                    applyWikilink(items[selected].title);
                  } else if (e.key === 'Escape') {
                    setPopup(null);
                  }
                }
              }}
              onBlur={() => setTimeout(() => setPopup(null), 150)}
            />
            {popup && items.length > 0 && (
              <div className="wl-popup" style={{ left: 12, bottom: 12 }}>
                <div className="px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-500 border-b border-ink-700">
                  Collega a una nota ({items.length})
                </div>
                {items.map((n, i) => (
                  <div
                    key={n.id}
                    className={`wl-item ${i === selected ? 'selected' : ''}`}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      applyWikilink(n.title);
                    }}
                    onMouseEnter={() => setSelected(i)}
                  >
                    <span className="text-slate-500 text-[10px] w-14 truncate">{n.type}</span>
                    <span className="truncate text-slate-200">{n.title}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {mode !== 'edit' && (
          <div className={`flex-1 min-w-0 overflow-y-auto p-4 bg-ink-850 ${mode === 'split' ? '' : ''}`}>
            <MathPreview markdown={note.content} onWikilink={onWikilink} />
          </div>
        )}
      </div>

      {/* barra di stato editor */}
      <div className="h-7 shrink-0 flex items-center gap-3 px-3 bg-ink-900 border-t border-ink-700 text-[10.5px] text-slate-500">
        <span className="truncate">{note.path}</span>
        <span>{note.content.length} caratteri</span>
        {saveError && <span className="text-rose-400 truncate">{saveError}</span>}
        <span className="ml-auto">
          frontmatter YAML · $LaTeX$ KaTeX · [[wikilink]] fuzzy
        </span>
      </div>
    </div>
  );
}
