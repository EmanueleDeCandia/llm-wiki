import { useEffect, useRef } from 'react';
import { api } from '../api/client';
import { useStore } from '../store';

const SAMPLE_CODE = `# Correlazione + scatter (matplotlib)
import polars as pl
corr = df.select(pl.corr('revenue', 'units')).item()
print('correlazione', round(corr, 4))

import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.scatter(df['units'].to_list(), df['revenue'].to_list(), alpha=0.7)
ax.set_title('revenue vs units')
plt.show()
`;

export function ConsolePane() {
  const code = useStore((s) => s.consoleCode);
  const dataset = useStore((s) => s.consoleDataset);
  const synthesize = useStore((s) => s.consoleSynthesize);
  const running = useStore((s) => s.consoleRunning);
  const entries = useStore((s) => s.consoleEntries);
  const figures = useStore((s) => s.consoleFigures);
  const logRef = useRef<HTMLDivElement>(null);
  const set = useStore((s) => s.set);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [entries]);

  const run = async () => {
    set({ consoleRunning: true, consoleEntries: [], consoleFigures: [] });
    useStore.getState().pushConsole({ kind: 'info', text: `▶ esecuzione sandbox (timeout 30s)${dataset ? ` · dataset ${dataset}` : ''}` });
    try {
      const res = await api.sandboxRun({
        code,
        task_name: 'analisi',
        dataset: dataset || null,
        synthesize,
      });
      if (res.stdout) useStore.getState().pushConsole({ kind: 'stdout', text: res.stdout });
      if (res.stderr) useStore.getState().pushConsole({ kind: 'stderr', text: res.stderr });
      useStore
        .getState()
        .pushConsole({
          kind: 'info',
          text: res.timed_out
            ? `⏱ timeout dopo ${res.duration_ms} ms`
            : res.ok
              ? `✔ exit ${res.exit_code} in ${res.duration_ms} ms · script ${res.script_path}`
              : `✖ exit ${res.exit_code} in ${res.duration_ms} ms`,
        });
      if (res.figures.length) {
        useStore.getState().set({ consoleFigures: res.figures });
        res.figures.forEach((f) =>
          useStore.getState().pushConsole({ kind: 'figure', text: f.name, figure: f }),
        );
      }
      if (res.synthesis_note) {
        useStore.getState().pushConsole({
          kind: 'info',
          text: `📝 sintesi compilata: wiki/synthesis/${res.synthesis_note}`,
        });
      }
    } catch (e) {
      useStore.getState().pushConsole({ kind: 'stderr', text: String(e) });
    } finally {
      set({ consoleRunning: false });
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* editor codice */}
      <div className="p-2 border-b border-ink-700 space-y-2">
        <div className="text-[10px] uppercase tracking-wide text-slate-500">
          Script Python — kernel isolato (30s) · {`{{df}}`} se dataset selezionato
        </div>
        <textarea
          value={code}
          onChange={(e) => set({ consoleCode: e.target.value })}
          placeholder="import polars as pl\nprint(df.head())"
          className="w-full h-36 bg-ink-850 border border-ink-600 rounded-lg p-2 font-mono text-[11.5px] text-emerald-200 outline-none focus:border-sky-500 resize-none"
          spellCheck={false}
        />
        <div className="flex items-center gap-2">
          <input
            value={dataset}
            onChange={(e) => set({ consoleDataset: e.target.value })}
            list="dataset-options"
            placeholder="dataset: es. datasets/sales.csv (opzionale)"
            className="flex-1 bg-ink-850 border border-ink-600 rounded px-2 py-1.5 text-[11px] text-slate-300 outline-none font-mono"
          />
          <datalist id="dataset-options">
            <option value="datasets/sales.csv" />
          </datalist>
          <label className="flex items-center gap-1.5 text-[10.5px] text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              className="accent-sky-500"
              checked={synthesize}
              onChange={(e) => set({ consoleSynthesize: e.target.checked })}
            />
            sintesi
          </label>
          <button
            onClick={run}
            disabled={running || !code.trim()}
            className="px-4 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-[12px] font-semibold"
          >
            {running ? '⏳' : '▶ Esegui'}
          </button>
        </div>
        <button
          onClick={() => set({ consoleCode: SAMPLE_CODE })}
          className="text-[10px] text-sky-400 hover:text-sky-300"
        >
          usa esempio correlazione+grafico
        </button>
      </div>

      {/* log */}
      <div ref={logRef} className="flex-1 overflow-y-auto bg-ink-950 p-2 font-mono text-[11px] leading-5">
        {entries.length === 0 && (
          <div className="text-slate-600">
            stdout/stderr dell'esecuzione sandbox appariranno qui. Le figure matplotlib vengono
            salvate automaticamente in sources/images/generated/.
          </div>
        )}
        {entries.map((e, i) => (
          <div key={i}>
            {e.kind === 'info' && <div className="text-sky-400/90">{e.text}</div>}
            {e.kind === 'stdout' && <pre className="whitespace-pre-wrap text-slate-200">{e.text}</pre>}
            {e.kind === 'stderr' && <pre className="whitespace-pre-wrap text-rose-300">{e.text}</pre>}
            {e.kind === 'figure' && e.figure && (
              <div className="my-1">
                <img src={e.figure.data_url} alt={e.figure.name} className="rounded border border-ink-700 max-h-52" />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* galleria figure */}
      {figures.length > 0 && (
        <div className="border-t border-ink-700 p-2 bg-ink-900">
          <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1.5">
            Figure ({figures.length}) — sources/images/generated/
          </div>
          <div className="flex gap-2 overflow-x-auto">
            {figures.map((f) => (
              <img
                key={f.path}
                src={f.data_url}
                alt={f.name}
                title={f.path}
                className="h-16 rounded border border-ink-700 shrink-0"
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
