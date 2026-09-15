import { useState } from 'react';
import type { TreeEntry } from '../types';

const ICONS: Record<string, string> = {
  pdf: '📕',
  epub: '📗',
  txt: '📄',
  md: '📝',
  docx: '📘',
  png: '🖼️',
  jpg: '🖼️',
  jpeg: '🖼️',
  webp: '🖼️',
  csv: '📊',
  tsv: '📊',
  parquet: '📊',
  sqlite: '🗄️',
  py: '🐍',
};

function iconFor(name: string) {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  if (ext === 'md') return '📝';
  return ICONS[ext] || '·';
}

// File eliminabili dall'utente (le sorgenti in sources/ sono immutabili)
const isDeletable = (p: string) =>
  p.startsWith('wiki/') || p.startsWith('scripts/generated/') || p.startsWith('sources/images/generated/');

export function FileTree({
  root,
  onOpenFile,
  onDeleteFile,
  activePath,
}: {
  root: TreeEntry | null;
  onOpenFile: (path: string) => void;
  onDeleteFile?: (path: string) => void;
  activePath?: string | null;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  if (!root) return <div className="p-3 text-[12px] text-slate-500">Caricamento albero…</div>;

  const toggle = (path: string) => {
    const next = new Set(collapsed);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setCollapsed(next);
  };

  const render = (node: TreeEntry, depth: number) => {
    const isDir = node.type === 'dir';
    const isCollapsed = collapsed.has(node.path);
    const showChildren = isDir && !isCollapsed;
    return (
      <div key={node.path}>
        <div
          className={`tree-row group ${activePath === node.path ? 'active' : 'text-slate-300'}`}
          style={{ paddingLeft: 8 + depth * 14 }}
          onClick={() => (isDir ? toggle(node.path) : onOpenFile(node.path))}
          title={node.path}
        >
          <span className="w-4 text-[10px] text-slate-500">{isDir ? (showChildren ? '▾' : '▸') : ''}</span>
          <span className="text-[13px]">{isDir ? (showChildren ? '📂' : '📁') : iconFor(node.name)}</span>
          <span className="truncate">{node.name}</span>
          {!isDir && isDeletable(node.path) && onDeleteFile && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDeleteFile(node.path);
              }}
              title={`Elimina ${node.path}`}
              className="ml-1 hidden group-hover:flex text-[11px] text-rose-400/80 hover:text-rose-300"
            >
              🗑
            </button>
          )}
          {node.path.includes('sources/') && !node.path.includes('generated') && (
            <span className="ml-auto text-[9px] text-slate-600 border border-ink-600 rounded px-1">RO</span>
          )}
        </div>
        {showChildren &&
          (node.children || []).map((c) => (
            <div key={c.path}>{render(c, depth + 1)}</div>
          ))}
      </div>
    );
  };

  return <div className="py-1 px-1 overflow-y-auto h-full">{(root.children || []).map((c) => render(c, 0))}</div>;
}
