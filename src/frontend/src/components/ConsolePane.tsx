import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';
import { useStore } from '../store';
import { ANALYSIS_TEMPLATES } from '../sandboxTemplates';
import type { TreeEntry } from '../types';

/** Raccolta i dataset disponibili (files in sources/datasets/) dall'albero del vault.
 *  I valori restituiti sono relativi a sources/ (es. 'datasets/sales.csv'). */
function collectDatasets(node: TreeEntry | null, out: string[] = []): string[] {
  if (!node) return out;
  if (node.type === 'file' && node.path.startsWith('sources/datasets/')) {
    out.push(node.path.replace('sources/', ''));
  } else {
    for (const c of node.children || []) collectDatasets(c, out);
  }
  return out;
}

function CleanupButton() {
  const [busy, setBusy] = useState(false);
  const cleanup = async () => {
    if (!window.confirm('Elimina gli artefatti delle analisi generate (script, figure e note di sintesi correlate)?')) return;
    setBusy(true);
    useStore.getState().pushConsole({ kind: 'info', text: '🧹 pulizia artefatti sandbox…' });
    try {
      const res = await api.sandboxCleanup(true);
      useStore
        .getState()
        .pushConsole({ kind: 'info', text: `✔ eliminati ${res.count} file · grafo ora con ${res.graph_nodes} nodi` });
      useStore.getState().refresh?.();
    } catch (e) {
      useStore.getState().pushConsole({ kind: 'stderr', text: String(e) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      onClick={cleanup}
      disabled={busy}
      title="Elimina script generati, figure e note di sintesi create dalla sandbox"
      className="text-[10px] text-rose-400/90 hover:text-rose-300 disabled:opacity-40"
    >
      {busy ? '🧹 pulizia in corso…' : '🧹 pulisci analisi generate'}
    </button>
  );
}

export function ConsolePane() {
  const code = useStore((s) => s.consoleCode);
  const dataset = useStore((s) => s.consoleDataset);
  const synthesize = useStore((s) => s.consoleSynthesize);
  const running = useStore((s) => s.consoleRunning);
  const entries = useStore((s) => s.consoleEntries);
  const figures = useStore((s) => s.consoleFigures);
  const tree = useStore((s) => s.tree);
  const [templateId, setTemplateId] = useState<string>('');
  const logRef = useRef<HTMLDivElement>(null);
  const set = useStore((s) => s.set);

  // dataset reali presenti nel vault (aggiornati a ogni refresh dell'albero)
  const datasets = useMemo(() => collectDatasets(tree).sort(), [tree]);
  const datasetOptions = dataset && !datasets.includes(dataset) ? [dataset, ...datasets] : datasets;
  const activeTemplate = ANALYSIS_TEMPLATES.find((t) => t.id === templateId);

  const applyTemplate = (id: string) => {
    setTemplateId(id);
    const t = ANALYSIS_TEMPLATES.find((x) => x.id === id);
    if (!t) return;
    set({ consoleCode: t.code });
    if (t.needsDataset && !dataset && datasets.length > 0) {
      set({ consoleDataset: datasets[0] });
      useStore
        .getState()
        .pushConsole({ kind: 'info', text: `dataset impostato automaticamente: ${datasets[0]}` });
    }
    useStore
      .getState()
      .pushConsole({ kind: 'info', text: `template "${t.label}" caricato — premi ▶ Esegui` });
  };

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
          <select
            value={templateId}
            onChange={(e) => applyTemplate(e.target.value)}
            className="flex-1 bg-ink-850 border border-ink-600 rounded px-2 py-1.5 text-[11px] text-slate-200 outline-none focus:border-sky-500"
            title="Carica un template di analisi nell'editor (il codice è poi modificabile)"
          >
            <option value="">📋 Template di analisi…</option>
            {ANALYSIS_TEMPLATES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        {activeTemplate && (
          <div className="text-[10px] text-slate-500 leading-4 -mt-1">{activeTemplate.description}</div>
        )}
        <div className="flex items-center gap-2">
          <select
            value={dataset}
            onChange={(e) => set({ consoleDataset: e.target.value })}
            className="flex-1 min-w-0 bg-ink-850 border border-ink-600 rounded px-2 py-1.5 text-[11px] text-slate-300 outline-none font-mono focus:border-sky-500"
            title="Dataset in sources/datasets/ caricato come df (polars)"
          >
            <option value="">— dataset da caricare come df —</option>
            {datasetOptions.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-[10.5px] text-slate-400 cursor-pointer shrink-0">
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
            className="px-4 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-[12px] font-semibold shrink-0"
          >
            {running ? '⏳' : '▶ Esegui'}
          </button>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-[10px] text-slate-600">
            Il codice è sempre modificabile nell'editor qui sopra.
          </span>
          <CleanupButton />
        </div>
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
