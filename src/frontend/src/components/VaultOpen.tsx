import { useState } from 'react';
import { api } from '../api/client';

const DEMO_VAULT = (import.meta as { env?: Record<string, string> }).env?.VITE_DEMO_VAULT ?? '~/llm-wiki/demo_vault';

const DEMO_PAPER = `# Attention-Based Sequence Models

The attention mechanism allocates model capacity to the most relevant parts of a sequence.
Its core weight is defined as $a_{ij} = \\frac{e^{q_i \\cdot k_j}}{\\sum_{k} e^{q_i \\cdot k_k}}$.

## Attention Mechanism

The attention mechanism computes a weighted sum of values: $z_i = \\sum_j a_{ij} v_j$.
It requires a query vector and a set of key-value pairs.
This operation is the foundation of modern sequence models.

## Training Procedure

Training uses stochastic gradient descent with learning rate $\\eta = 0.001$.
The loss is the cross-entropy between targets and predictions.
Convergence typically occurs within a few epochs on small corpora.

## Evaluation

Evaluation reports accuracy on a held-out set.
Standard metrics include precision and recall.
`;

const DEMO_CSV = 'revenue,units,region\n';

export function VaultOpenScreen({ onOpen }: { onOpen: (root: string) => void }) {
  const [path, setPath] = useState(DEMO_VAULT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = async (target: string, loadDemo: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.openVault(target);
      if (loadDemo) {
        // Documentazione demo: mostra la pipeline A completa (note + grafo).
        await api.ingest(new File([DEMO_PAPER], 'attention_paper.txt', { type: 'text/plain' }));
        let csv = DEMO_CSV;
        for (let i = 0; i < 40; i++) {
          const units = 10 + Math.floor(Math.random() * 90);
          csv += `${(units * (8 + Math.random() * 6)).toFixed(2)},${units},${i % 2 ? 'N' : 'S'}\n`;
        }
        await api.ingest(new File([csv], 'sales.csv', { type: 'text/csv' }));
      }
      onOpen(res.root);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full flex items-center justify-center p-8">
      <div className="max-w-xl w-full bg-ink-900 border border-ink-700 rounded-2xl p-8 shadow-2xl">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 flex items-center justify-center text-lg font-bold text-white">
            W
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-50">LLM Wiki Desktop</h1>
            <p className="text-[12px] text-slate-400">
              Piattaforma local-first per la conoscenza compilata
            </p>
          </div>
        </div>

        <p className="text-[12.5px] text-slate-400 mt-4 leading-relaxed">
          Apri un vault locale per iniziare. La topologia{' '}
          <code className="text-emerald-300">sources/ · wiki/ · _index/ · scripts/</code> viene
          verificata e inizializzata automaticamente.
        </p>

        <label className="block mt-5 text-[11px] uppercase tracking-wide text-slate-500">
          Percorso del vault (sul server del sidecar)
        </label>
        <input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          className="mt-1 w-full bg-ink-850 border border-ink-600 rounded-lg px-3 py-2 text-[13px] text-slate-100 outline-none focus:border-sky-500 font-mono"
          placeholder="/percorso/assoluto/vault"
        />

        {error && (
          <div className="mt-3 text-[12px] text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg p-2">
            {error}
          </div>
        )}

        <div className="flex gap-2 mt-5">
          <button
            disabled={busy}
            onClick={() => open(path, false)}
            className="flex-1 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-[13px] font-semibold"
          >
            {busy ? 'Apertura…' : 'Apri vault'}
          </button>
          <button
            disabled={busy}
            onClick={() => open(DEMO_VAULT, true)}
            className="flex-1 py-2.5 rounded-lg bg-ink-700 hover:bg-ink-600 disabled:opacity-50 text-slate-100 text-[13px] font-semibold"
            title="Crea il vault demo e ingera un paper + un dataset per mostrare la pipeline"
          >
            ✨ Vault demo
          </button>
        </div>

        <div className="mt-6 grid grid-cols-3 gap-3 text-center">
          {[
            ['📄', 'Ingestione', 'PDF · documenti · immagini · dataset'],
            ['🧠', 'Note atomiche', 'frontmatter YAML + [[wikilink]]'],
            ['📊', 'Sandbox Python', 'correlazioni, grafici, lint'],
          ].map(([icon, title, sub]) => (
            <div key={title} className="bg-ink-850 border border-ink-700 rounded-xl p-3">
              <div className="text-lg">{icon}</div>
              <div className="text-[12px] font-semibold text-slate-200 mt-1">{title}</div>
              <div className="text-[10.5px] text-slate-500 mt-0.5">{sub}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
