export type NoteType = 'concept' | 'entity' | 'dataset' | 'synthesis' | 'source';

export interface GraphNode {
  id: string;
  title: string;
  type: NoteType;
  tags: string[];
  aliases: string[];
  abstract: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: 'prerequisite' | 'related' | 'conflict' | 'source';
}

export interface GraphData {
  version: number;
  generated_at: string;
  node_count: number;
  edge_count: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface NoteSummary {
  id: string;
  title: string;
  type: string;
  tags: string[];
  aliases: string[];
  abstract: string;
}

export interface TreeEntry {
  name: string;
  path: string;
  type: 'dir' | 'file';
  children?: TreeEntry[];
  size?: number;
}

export interface LintSummary {
  ok: boolean;
  clean: boolean;
  node_count: number;
  edge_count: number;
  orphan_links: { note: string; target: string }[];
  isolated_nodes: string[];
  components: number;
  conflicts: { a: string; b: string; metric: string; value_a: string | number; value_b: string | number; detail?: string }[];
  structural_issues: { note: string; section: string }[];
  provenance_missing: string[];
  report_path: string;
}

export interface SandboxFigure {
  name: string;
  path: string;
  size_bytes: number;
  data_url: string;
}

export interface SandboxResult {
  task_id: string;
  script_path: string;
  exit_code: number | null;
  ok: boolean;
  stdout: string;
  stderr: string;
  duration_ms: number;
  timed_out: boolean;
  error: string | null;
  figures: SandboxFigure[];
  synthesis_note: string | null;
}

export interface QueryResult {
  provider: string;
  answer_markdown: string;
  citations: { note: string; title: string; score: number; excerpt: string }[];
}

export interface LLMStatus {
  provider: string;
  model: string;
  configured: boolean;
  reachable: boolean;
  description: string;
}

export interface Health {
  ok: boolean;
  app: string;
  version: string;
  vault_open: boolean;
  vault_root: string | null;
  llm: LLMStatus;
  sandbox_timeout_seconds: number;
}

export interface IngestResult {
  source_path: string;
  branch: string;
  parser: string;
  compiler: string;
  notes_created: string[];
  notes_skipped: string[];
  index_updated: boolean;
  sources_integrity_ok: boolean;
  sources_altered: string[];
  messages: string[];
}

export interface FolderIngestFile {
  name: string;
  status: 'ok' | 'skipped' | 'error';
  source_path?: string;
  notes: number;
  parser?: string;
  error?: string;
}

export interface FolderIngestResult {
  files: FolderIngestFile[];
  ingested: number;
  skipped: number;
  errors: number;
}
