import { useStore } from '../store';
import type { Health } from '../types';

function Dot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-slate-400" title={label}>
      <span className={`w-2 h-2 rounded-full ${ok ? 'bg-emerald-400' : 'bg-rose-500'}`} />
      {label}
    </span>
  );
}

export function TopBar({
  health,
  onRefresh,
  onRebuildIndex,
  onLint,
}: {
  health: Health | null;
  onRefresh: () => void;
  onRebuildIndex: () => void;
  onLint: () => void;
}) {
  const vaultOpen = useStore((s) => s.vaultOpen);
  const toast = useStore((s) => s.toast);

  return (
    <header className="h-12 flex items-center gap-4 px-4 bg-ink-900 border-b border-ink-700 shrink-0">
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-sky-500 to-indigo-600 flex items-center justify-center text-[13px] font-bold text-white">
          W
        </div>
        <div className="leading-tight">
          <div className="text-[13px] font-semibold text-slate-100">LLM Wiki Desktop</div>
          <div className="text-[10px] text-slate-500">conoscenza compilata · local-first</div>
        </div>
      </div>

      <div className="flex items-center gap-3 ml-4">
        <Dot ok={health?.ok ?? false} label="sidecar" />
        <Dot ok={vaultOpen} label="vault" />
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full border ${
            health?.llm?.configured
              ? 'border-amber-500/50 text-amber-300'
              : 'border-emerald-500/40 text-emerald-300'
          }`}
          title={health?.llm?.description}
        >
          {health?.llm?.configured ? `LLM: ${health.llm.provider}` : 'offline · deterministico'}
        </span>
      </div>

      <div className="flex-1" />

      {toast && (
        <div className="text-[11px] text-sky-300 bg-ink-800 border border-ink-600 rounded px-2 py-1 max-w-md truncate">
          {toast}
        </div>
      )}

      <div className="flex items-center gap-2">
        {vaultOpen && (
          <>
            <button
              onClick={onLint}
              className="text-[11.5px] px-3 py-1.5 rounded-md bg-ink-800 hover:bg-ink-700 border border-ink-600 text-slate-200"
            >
              ▶ Lint
            </button>
            <button
              onClick={onRebuildIndex}
              className="text-[11.5px] px-3 py-1.5 rounded-md bg-ink-800 hover:bg-ink-700 border border-ink-600 text-slate-200"
            >
              ↻ Indice
            </button>
          </>
        )}
        <button
          onClick={onRefresh}
          className="text-[11.5px] px-3 py-1.5 rounded-md bg-ink-800 hover:bg-ink-700 border border-ink-600 text-slate-200"
        >
          ⟳ Aggiorna
        </button>
      </div>
    </header>
  );
}
