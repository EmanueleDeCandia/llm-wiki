import { useState } from 'react';
import { api } from '../api/client';
import { MathPreview } from '../lib/markdown';
import { useStore } from '../store';

export function LintPanel() {
  const lint = useStore((s) => s.lint);
  const running = useStore((s) => s.lintRunning);
  const [report, setReport] = useState<string | null>(null);
  const set = useStore((s) => s.set);

  const run = async () => {
    set({ lintRunning: true });
    try {
      const res = await api.lintRun();
      set({ lint: res });
      const rep = await api.lintReport();
      setReport(rep.content);
    } catch (e) {
      set({ statusMessage: `Lint: ${String(e)}` });
    } finally {
      set({ lintRunning: false });
    }
  };

  const Section = ({ title, children, tone }: { title: string; children: React.ReactNode; tone?: 'ok' | 'warn' }) => (
    <div className={`rounded-lg border p-2 ${tone === 'warn' ? 'border-amber-500/40 bg-amber-500/5' : tone === 'ok' ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-ink-700 bg-ink-850'}`}>
      <div className="text-[11px] font-semibold text-slate-200">{title}</div>
      <div className="mt-1 text-[11px] text-slate-400 space-y-0.5">{children}</div>
    </div>
  );

  return (
    <div className="h-full flex flex-col">
      <div className="p-2 border-b border-ink-700 flex items-center gap-2">
        <button
          onClick={run}
          disabled={running}
          className="px-4 py-1.5 rounded-md bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-[12px] font-semibold"
        >
          {running ? '⏳ Audit in corso…' : '▶ Esegui Knowledge Linting'}
        </button>
        <span className="text-[10px] text-slate-500">Pipeline B → _index/lint_report.md</span>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {!lint && (
          <div className="text-[12px] text-slate-500 p-3">
            Non hai ancora eseguito l'audit. Il linting costruisce G = (V, E) e rileva link
            orfani, nodi isolati, cluster disconnessi e conflitti semantici.
          </div>
        )}
        {lint && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Section title="Nodi / archi">
                {lint.node_count} nodi · {lint.edge_count} archi
              </Section>
              <Section title={lint.clean ? 'Stato: pulito ✔' : 'Stato: anomalie'} tone={lint.clean ? 'ok' : 'warn'}>
                orfani {lint.orphan_links.length} · isolati {lint.isolated_nodes.length} · cluster {lint.components}
              </Section>
            </div>

            {lint.orphan_links.length > 0 && (
              <Section title={`🔗 Link orfani (${lint.orphan_links.length})`} tone="warn">
                {lint.orphan_links.map((o, i) => (
                  <div key={i} className="font-mono text-[10.5px] truncate">
                    {o.note} → [[{o.target}]]
                  </div>
                ))}
              </Section>
            )}
            {lint.isolated_nodes.length > 0 && (
              <Section title={`🏝 Nodi isolati (${lint.isolated_nodes.length})`} tone="warn">
                {lint.isolated_nodes.map((n) => (
                  <div key={n} className="font-mono text-[10.5px] truncate">{n}</div>
                ))}
              </Section>
            )}
            {lint.conflicts.length > 0 && (
              <Section title={`⚠️ Conflitti semantici (${lint.conflicts.length})`} tone="warn">
                {lint.conflicts.map((c, i) => (
                  <div key={i} className="text-[10.5px]">
                    <span className="font-mono">{c.a} ↔ {c.b}</span> — {c.metric}: {c.value_a} ≠ {c.value_b}
                    {c.detail ? ` (${c.detail})` : ''}
                  </div>
                ))}
              </Section>
            )}
            {lint.structural_issues.length > 0 && (
              <Section title={`📐 Struttura non conforme (${lint.structural_issues.length})`}>
                {lint.structural_issues.slice(0, 8).map((s, i) => (
                  <div key={i} className="font-mono text-[10.5px] truncate">
                    {s.note} — manca «{s.section}»
                  </div>
                ))}
              </Section>
            )}
            {lint.provenance_missing.length > 0 && (
              <Section title={`📎 Provenienza mancante (${lint.provenance_missing.length})`}>
                {lint.provenance_missing.map((n) => (
                  <div key={n} className="font-mono text-[10.5px] truncate">{n}</div>
                ))}
              </Section>
            )}

            {report && (
              <details className="rounded-lg border border-ink-700 bg-ink-850 p-2">
                <summary className="text-[11px] font-semibold text-slate-200 cursor-pointer">
                  📄 _index/lint_report.md
                </summary>
                <div className="mt-2 max-h-64 overflow-y-auto">
                  <MathPreview markdown={report} />
                </div>
              </details>
            )}
          </>
        )}
      </div>
    </div>
  );
}
