import { api } from '../api/client';
import { MathPreview } from '../lib/markdown';
import { useStore } from '../store';

export function QueryPanel({ onOpenNote }: { onOpenNote: (path: string, title: string) => void }) {
  const question = useStore((s) => s.query);
  const result = useStore((s) => s.queryResult);
  const running = useStore((s) => s.queryRunning);
  const error = useStore((s) => s.queryError);
  const health = useStore((s) => s.health);
  const set = useStore((s) => s.set);

  const ask = async () => {
    if (!question.trim()) return;
    set({ queryRunning: true, queryError: null });
    try {
      const res = await api.query(question);
      set({ queryResult: res });
    } catch (e) {
      set({ queryError: String(e) });
    } finally {
      set({ queryRunning: false });
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="p-2 border-b border-ink-700 space-y-2">
        <div className="text-[10px] uppercase tracking-wide text-slate-500">
          Query sulla conoscenza compilata · provider:{' '}
          <span className="text-sky-300">{health?.llm?.configured ? health.llm.provider : 'deterministico offline'}</span>
        </div>
        <div className="flex gap-2">
          <textarea
            value={question}
            onChange={(e) => set({ query: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ask();
            }}
            placeholder="Es. Cos'è l'attention mechanism?  (Ctrl+Invio per inviare)"
            className="flex-1 h-16 bg-ink-850 border border-ink-600 rounded-lg p-2 text-[12px] text-slate-200 outline-none focus:border-sky-500 resize-none"
          />
          <button
            onClick={ask}
            disabled={running || !question.trim()}
            className="self-stretch px-4 rounded-md bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-[12px] font-semibold"
          >
            {running ? '⏳' : '⌕'}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {error && <div className="text-[12px] text-rose-300 mb-2">{error}</div>}
        {!result && !error && (
          <div className="text-[12px] text-slate-500 leading-relaxed">
            L'interrogazione usa <b>solo</b> le note atomiche dell'indice, seguendo i
            collegamenti <code className="text-sky-400">[[...]]</code>.
            <br />
            <br />
            In modalità offline (default) la risposta è una composizione deterministica
            tracciabile: zero allucinazioni, zero modelli. Con un provider LLM configurato il
            contratto di risposta resta identico.
          </div>
        )}
        {result && (
          <div>
            <div
              className={`text-[10px] px-2 py-1 rounded mb-2 border inline-block ${
                result.provider.startsWith('deterministic')
                  ? 'text-emerald-300 border-emerald-500/40'
                  : 'text-amber-300 border-amber-500/40'
              }`}
            >
              provider: {result.provider}
            </div>
            <MathPreview
              markdown={result.answer_markdown}
              onWikilink={(t) => {
                const note = useStore.getState().notes.find((n) => n.title === t || n.id.endsWith(t + '.md'));
                if (note) onOpenNote(note.id, note.title);
              }}
            />
            {result.citations.length > 0 && (
              <div className="mt-3">
                <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                  Citazioni ({result.citations.length})
                </div>
                {result.citations.map((c) => (
                  <button
                    key={c.note}
                    onClick={() => onOpenNote(c.note, c.title)}
                    className="block w-full text-left text-[11px] text-slate-400 hover:text-sky-300 py-1 border-b border-ink-800 truncate"
                  >
                    [[{c.title}]] <span className="text-slate-600">score {c.score}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
