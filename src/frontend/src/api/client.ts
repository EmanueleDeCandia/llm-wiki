import type {
  GraphData,
  Health,
  IngestResult,
  LintSummary,
  NoteSummary,
  QueryResult,
  SandboxResult,
  TreeEntry,
} from '../types';

const BASE = '/api/v1';

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* ignore */
    }
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>('/health'),
  openVault: (path: string, templateRoot?: string) =>
    req<{ root: string; created_dirs: string[]; missing_before: string[]; index_initialized: boolean; llm_status: import('../types').LLMStatus }>(
      '/vault/open',
      { method: 'POST', body: JSON.stringify({ path, template_root: templateRoot ?? null }) },
    ),
  tree: () => req<TreeEntry>('/vault/tree'),
  notes: () => req<NoteSummary[]>('/notes'),
  readNote: (path: string) =>
    req<{ path: string; frontmatter: Record<string, unknown>; body: string; raw: string }>(`/notes/${path}`),
  saveNote: (path: string, content: string) =>
    req<{ path: string; saved: boolean; missing_sections: string[] }>(`/notes/${path}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }),
  deleteNote: (path: string) => req<{ deleted: boolean }>(`/notes/${path}`, { method: 'DELETE' }),
  deleteFile: (path: string) => req<{ path: string; deleted: boolean }>(`/files/${path}`, { method: 'DELETE' }),
  sandboxCleanup: (includeSynthesis = true) =>
    req<{ deleted: string[]; count: number; graph_nodes: number }>('/sandbox/cleanup', {
      method: 'POST',
      body: JSON.stringify({ include_synthesis: includeSynthesis }),
    }),
  graph: () => req<GraphData>('/graph/nodes'),
  ingest: (file: File, branch?: string) =>
    new Promise<IngestResult>((resolve, reject) => {
      const fd = new FormData();
      fd.append('file', file);
      const qs = branch ? `?branch=${encodeURIComponent(branch)}` : '';
      fetch(`${BASE}/ingest/file${qs}`, { method: 'POST', body: fd })
        .then(async (res) => {
          if (!res.ok) {
            let detail = res.statusText;
            try {
              const b = await res.json();
              detail = typeof b.detail === 'string' ? b.detail : JSON.stringify(b.detail ?? b);
            } catch {
              /* ignore */
            }
            throw new Error(`API ${res.status}: ${detail}`);
          }
          resolve((await res.json()) as IngestResult);
        })
        .catch(reject);
    }),
  lintRun: () => req<LintSummary>('/lint/run', { method: 'POST' }),
  lintReport: () => req<{ path: string; content: string }>('/lint/report'),
  sandboxRun: (payload: {
    code: string;
    task_name?: string;
    dataset?: string | null;
    synthesize?: boolean;
  }) => req<SandboxResult>('/sandbox/run', { method: 'POST', body: JSON.stringify(payload) }),
  query: (question: string, top_k = 5) =>
    req<QueryResult>('/agent/query', { method: 'POST', body: JSON.stringify({ question, top_k }) }),
  indexRebuild: () => req<{ rebuilt: boolean; nodes: number; edges: number }>('/index/rebuild', { method: 'POST' }),
  fileUrl: (path: string) => `${BASE}/files/${path}`,
};
