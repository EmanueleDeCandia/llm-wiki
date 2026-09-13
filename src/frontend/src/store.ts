import { create } from 'zustand';
import type {
  GraphData,
  Health,
  LintSummary,
  NoteSummary,
  QueryResult,
  SandboxFigure,
  SandboxResult,
  TreeEntry,
} from './types';

export interface OpenNote {
  path: string;
  content: string;
  savedContent: string;
  dirty: boolean;
}

export interface FilePreview {
  path: string;
  url?: string;
  text?: string;
}

export interface ConsoleEntry {
  kind: 'command' | 'stdout' | 'stderr' | 'info' | 'figure';
  text: string;
  figure?: SandboxFigure;
  at: number;
}

interface State {
  health: Health | null;
  online: boolean;
  vaultOpen: boolean;
  filePreview: FilePreview | null;

  tree: TreeEntry | null;
  treeLoading: boolean;

  notes: NoteSummary[];
  openNotes: OpenNote[];
  activeNote: string | null;

  graph: GraphData | null;
  graphTagFilter: string[];
  graphSearch: string;

  lint: LintSummary | null;
  lintRunning: boolean;

  consoleCode: string;
  consoleDataset: string;
  consoleSynthesize: boolean;
  consoleRunning: boolean;
  consoleEntries: ConsoleEntry[];
  consoleFigures: SandboxFigure[];

  query: string;
  queryResult: QueryResult | null;
  queryRunning: boolean;
  queryError: string | null;

  statusMessage: string | null;
  toast: string | null;

  set: (partial: Partial<State>) => void;
  pushConsole: (e: Omit<ConsoleEntry, 'at'>) => void;
  openNote: (path: string, content: string) => void;
  closeNote: (path: string) => void;
  noteContent: (path: string, content: string) => void;
  markSaved: (path: string, content: string) => void;
}

export const useStore = create<State>((set, get) => ({
  health: null,
  online: false,
  vaultOpen: false,
  filePreview: null,

  tree: null,
  treeLoading: false,

  notes: [],
  openNotes: [],
  activeNote: null,

  graph: null,
  graphTagFilter: [],
  graphSearch: '',

  lint: null,
  lintRunning: false,

  consoleCode: '',
  consoleDataset: '',
  consoleSynthesize: false,
  consoleRunning: false,
  consoleEntries: [],
  consoleFigures: [],

  query: '',
  queryResult: null,
  queryRunning: false,
  queryError: null,

  statusMessage: null,
  toast: null,

  set: (partial) => set(partial),

  pushConsole: (e) =>
    set({ consoleEntries: [...get().consoleEntries.slice(-400), { ...e, at: Date.now() }] }),

  openNote: (path, content) => {
    const notes = get().openNotes;
    if (notes.some((n) => n.path === path)) {
      set({ activeNote: path });
      return;
    }
    set({
      openNotes: [...notes, { path, content, savedContent: content, dirty: false }],
      activeNote: path,
    });
  },

  closeNote: (path) => {
    const rest = get().openNotes.filter((n) => n.path !== path);
    set({
      openNotes: rest,
      activeNote: get().activeNote === path ? rest[rest.length - 1]?.path ?? null : get().activeNote,
    });
  },

  noteContent: (path, content) => {
    set({
      openNotes: get().openNotes.map((n) =>
        n.path === path ? { ...n, content, dirty: content !== n.savedContent } : n,
      ),
    });
  },

  markSaved: (path, content) => {
    set({
      openNotes: get().openNotes.map((n) =>
        n.path === path ? { ...n, content, savedContent: content, dirty: false } : n,
      ),
    });
  },
}));
