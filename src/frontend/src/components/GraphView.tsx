import ForceGraph2D from 'react-force-graph-2d';
import { useEffect, useMemo, useRef } from 'react';
import { useStore } from '../store';
import type { GraphData, GraphNode } from '../types';

export const NODE_COLORS: Record<string, string> = {
  concept: '#38bdf8',
  entity: '#34d399',
  dataset: '#fbbf24',
  synthesis: '#f472b6',
  source: '#64748b',
};

export const TYPE_LABELS: Record<string, string> = {
  concept: 'Concetto',
  entity: 'Entità',
  dataset: 'Dataset',
  synthesis: 'Sintesi',
  source: 'Sorgente',
};

export function GraphView({
  graph,
  onNodeClick,
  height,
}: {
  graph: GraphData;
  onNodeClick?: (node: GraphNode) => void;
  height: number | string;
}) {
  const tagFilter = useStore((s) => s.graphTagFilter);
  const search = useStore((s) => s.graphSearch);
  const gRef = useRef<unknown>(null);

  const { nodes, links, allTags } = useMemo(() => {
    const q = search.trim().toLowerCase();
    const idSet = new Set<string>();
    const filtered = graph.nodes.filter((n) => {
      if (tagFilter.length && !n.tags.some((t) => tagFilter.includes(t))) return false;
      if (q) {
        const hay = `${n.title} ${n.abstract} ${n.id} ${n.aliases.join(' ')}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    filtered.forEach((n) => idSet.add(n.id));
    const nodes = filtered.map((n) => ({
      id: n.id,
      name: n.title,
      type: n.type,
      abstract: n.abstract,
      color: NODE_COLORS[n.type] || '#94a3b8',
      val: n.type === 'source' ? 0.8 : 1.6,
    }));
    const links = graph.edges.filter((e) => {
      const s = typeof e.source === 'object' ? (e.source as { id: string }).id : e.source;
      const t = typeof e.target === 'object' ? (e.target as { id: string }).id : e.target;
      return idSet.has(s) && idSet.has(t);
    });
    const allTags = Array.from(new Set(graph.nodes.flatMap((n) => n.tags))).sort();
    return { nodes, links, allTags };
  }, [graph, tagFilter, search]);

  useEffect(() => {
    // centraggio alla prima resa
    const t = setTimeout(() => {
      const api = gRef.current as { zoomToFit?: (ms?: number, fit?: number) => void } | null;
      api?.zoomToFit?.(300, 0.5);
    }, 350);
    return () => clearTimeout(t);
  }, [graph]);

  if (graph.node_count === 0) {
    return (
      <div style={{ height }} className="flex items-center justify-center text-[12px] text-slate-500">
        Vault vuoto: ingerisci una fonte per popolare il grafo.
      </div>
    );
  }

  return (
    <div className="relative" style={{ height }}>
      <ForceGraph2D
        ref={gRef as never}
        graphData={{ nodes, links }}
        nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, scale: number) => {
          const r = (node.val || 1) * 3;
          ctx.globalAlpha = 0.95;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r / scale + 1.5, 0, 2 * Math.PI);
          ctx.fillStyle = node.color;
          ctx.fill();
          if (scale > 1.2) {
            ctx.font = `${10 / scale}px ui-sans-serif`;
            ctx.fillStyle = '#cbd5e1';
            ctx.textAlign = 'center';
            const label = (node.name as string).slice(0, 28);
            ctx.fillText(label, node.x, node.y + r / scale + 10 / scale);
          }
        }}
        linkColor={(l: any) => {
          const k = l.kind ?? l.link?.kind;
          if (k === 'conflict') return 'rgba(244,63,94,0.35)';
          if (k === 'source') return 'rgba(100,116,139,0.25)';
          if (k === 'prerequisite') return 'rgba(251,191,36,0.4)';
          return 'rgba(148,163,184,0.3)';
        }}
        linkDirectionalArrowLength={(l: any) => (l.kind === 'prerequisite' ? 3 : 0)}
        linkDirectionalArrowRelPos={1}
        onNodeClick={(n: any) => onNodeClick?.(n as GraphNode)}
        onNodeDragEnd={(n: any) => {
          n.fx = null;
          n.fy = null;
        }}
        width={undefined}
        height={height as number}
      />
      {/* legenda + filtri */}
      <div className="absolute top-2 left-2 bg-ink-900/90 border border-ink-700 rounded-lg p-2 space-y-2 w-44">
        <input
          value={search}
          onChange={(e) => useStore.getState().set({ graphSearch: e.target.value })}
          placeholder="Cerca nel grafo…"
          className="w-full bg-ink-850 border border-ink-600 rounded px-2 py-1 text-[11px] text-slate-200 outline-none focus:border-sky-500"
        />
        <div className="flex flex-wrap gap-1">
          {Object.entries(NODE_COLORS).map(([t, c]) => (
            <span key={t} className="flex items-center gap-1 text-[10px] text-slate-400">
              <span className="w-2 h-2 rounded-full" style={{ background: c }} />
              {TYPE_LABELS[t]}
            </span>
          ))}
        </div>
        {allTags.length > 0 && (
          <div className="max-h-24 overflow-y-auto space-y-0.5">
            {allTags.slice(0, 12).map((t) => (
              <label key={t} className="flex items-center gap-1.5 text-[10.5px] text-slate-400 cursor-pointer">
                <input
                  type="checkbox"
                  className="accent-sky-500"
                  checked={tagFilter.includes(t)}
                  onChange={(e) => {
                    const cur = useStore.getState().graphTagFilter;
                    useStore.getState().set({
                      graphTagFilter: e.target.checked ? [...cur, t] : cur.filter((x) => x !== t),
                    });
                  }}
                />
                {t}
              </label>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
