export type FileItem = {
  id: string;
  name: string;
  size: number;
  duration: number;
  status: 'queued' | 'processing' | 'done' | 'error';
  progress: number;
  phase: number;
  phaseText?: string;
  errorText?: string;
  eta?: string;
  path?: string;
  outputHtml?: string;
  outputDir?: string;
  completedAt?: number;
};

export function getPendingFiles(files: FileItem[]): FileItem[] {
  return files.filter(f => f.status !== 'done');
}

/** Always returns a new sorted array. Wrap in useMemo to avoid per-render allocations. */
export function getDoneFiles(files: FileItem[]): FileItem[] {
  return [...files.filter(f => f.status === 'done')]
    .sort((a, b) => (b.completedAt ?? 0) - (a.completedAt ?? 0));
}

export type FileDescriptor = {
  id: string;
  path?: string;
  name: string;
  size: number;
  duration?: number;
};

export type AppStatus = 'idle' | 'processing' | 'canceling';

export type ProcessDonePayload = {
  cancelled?: boolean;
  completed?: number;
  failed?: number;
  total?: number;
};

export type SetCurrentFilePayload = {
  index: number;
  id: string;
  total: number;
};

export type FileDonePayload = {
  index: number;
  id: string;
  output_html: string;
  output_dir: string;
};

export type FileFailedPayload = {
  index: number;
  id: string;
  error: string;
};

export type WorkTotalsPayload = {
  chunks?: number | null;
  macro?: number | null;
  boundary?: number | null;
};

export type WorkDonePayload = {
  kind: 'chunks' | 'macro' | 'boundary';
  done: number;
  total?: number | null;
};

export type StepTimePayload = {
  kind: 'chunks' | 'macro' | 'boundary';
  seconds: number;
  done?: number | null;
  total?: number | null;
};

export type StepMetricEntry = {
  avgSeconds: number;
  done: number;
  total: number;
};

export type ProcessingState = {
  files: FileItem[];
  structuralVersion: number;
  appState: AppStatus;
  currentPhase: string;
  activeProgress: number;
  workTotals: {
    chunks: number;
    macro: number;
    boundary: number;
  };
  workDone: {
    chunks: number;
    macro: number;
    boundary: number;
  };
  stepMetrics: {
    chunks: StepMetricEntry | null;
    macro: StepMetricEntry | null;
    boundary: StepMetricEntry | null;
  };
};

export type ProcessingAction =
  | { type: 'queue/add'; files: FileItem[] }
  | { type: 'queue/remove'; id: string }
  | { type: 'queue/reorder'; fromIndex: number; toIndex: number }
  | { type: 'queue/update_source'; id: string; path?: string; name?: string; size?: number; duration?: number }
  | { type: 'queue/clear_completed' }
  | { type: 'queue/retry_failed' }
  | { type: 'queue/clear_all' }
  | { type: 'app/set_status'; status: AppStatus }
  | { type: 'bridge/update_progress'; value: number }
  | { type: 'bridge/update_phase'; text: string }
  | { type: 'bridge/process_done'; data: ProcessDonePayload }
  | { type: 'bridge/set_work_totals'; data: WorkTotalsPayload }
  | { type: 'bridge/update_work_done'; data: WorkDonePayload }
  | { type: 'bridge/register_step_time'; data: StepTimePayload }
  | { type: 'bridge/set_current_file'; data: SetCurrentFilePayload }
  | { type: 'bridge/file_done'; data: FileDonePayload }
  | { type: 'bridge/file_failed'; data: FileFailedPayload };

export const initialProcessingState: ProcessingState = {
  files: [],
  structuralVersion: 0,
  appState: 'idle',
  currentPhase: '',
  activeProgress: 0,
  workTotals: { chunks: 0, macro: 0, boundary: 0 },
  workDone: { chunks: 0, macro: 0, boundary: 0 },
  stepMetrics: { chunks: null, macro: null, boundary: null },
};

export function processingReducer(state: ProcessingState, action: ProcessingAction): ProcessingState {
  switch (action.type) {
    case 'queue/add':
      return { ...state, structuralVersion: state.structuralVersion + 1, files: [...state.files, ...action.files] };
    case 'queue/remove':
      return { ...state, structuralVersion: state.structuralVersion + 1, files: state.files.filter(file => file.id !== action.id) };
    case 'queue/reorder': {
      const { fromIndex, toIndex } = action;
      if (fromIndex === toIndex) return state;
      if (fromIndex < 0 || fromIndex >= state.files.length) return state;
      if (toIndex < 0 || toIndex >= state.files.length) return state;
      const files = [...state.files];
      const [moved] = files.splice(fromIndex, 1);
      files.splice(toIndex, 0, moved);
      return { ...state, structuralVersion: state.structuralVersion + 1, files };
    }
    case 'queue/update_source':
      return {
        ...state,
        structuralVersion: state.structuralVersion + 1,
        files: state.files.map(file =>
          file.id === action.id
            ? {
                ...file,
                path: action.path ?? file.path,
                name: action.name ?? file.name,
                size: action.size ?? file.size,
                duration: action.duration ?? file.duration,
              }
            : file,
        ),
      };
    case 'queue/clear_completed':
      return { ...state, structuralVersion: state.structuralVersion + 1, files: state.files.filter(file => file.status !== 'done') };
    case 'queue/retry_failed':
      return {
        ...state,
        structuralVersion: state.structuralVersion + 1,
        files: state.files.map(file =>
          file.status === 'error'
            ? { ...file, status: 'queued', progress: 0, phase: 0, phaseText: undefined, errorText: undefined }
            : file,
        ),
      };
    case 'queue/clear_all':
      return { ...state, structuralVersion: state.structuralVersion + 1, files: [] };
    case 'app/set_status':
      return { ...state, appState: action.status };
    case 'bridge/update_progress':
      return { ...state, activeProgress: Math.round(action.value * 100) };
    case 'bridge/update_phase':
      return { ...state, currentPhase: action.text };
    case 'bridge/process_done':
      return {
        ...state,
        structuralVersion: action.data?.cancelled ? state.structuralVersion + 1 : state.structuralVersion,
        appState: 'idle',
        currentPhase: '',
        activeProgress: action.data?.cancelled ? 0 : state.activeProgress,
        workTotals: action.data?.cancelled ? { chunks: 0, macro: 0, boundary: 0 } : state.workTotals,
        workDone: action.data?.cancelled ? { chunks: 0, macro: 0, boundary: 0 } : state.workDone,
        stepMetrics: action.data?.cancelled ? { chunks: null, macro: null, boundary: null } : state.stepMetrics,
        files: action.data?.cancelled
          ? state.files.map(file =>
              file.status === 'processing'
                ? { ...file, status: 'queued', progress: 0, phase: 0, phaseText: undefined }
                : file,
            )
          : state.files,
      };
    case 'bridge/set_work_totals':
      return {
        ...state,
        workTotals: {
          chunks: Number(action.data.chunks ?? state.workTotals.chunks ?? 0),
          macro: Number(action.data.macro ?? state.workTotals.macro ?? 0),
          boundary: Number(action.data.boundary ?? state.workTotals.boundary ?? 0),
        },
      };
    case 'bridge/update_work_done':
      return {
        ...state,
        workDone: {
          ...state.workDone,
          [action.data.kind]: Number(action.data.done ?? 0),
        },
      };
    case 'bridge/register_step_time': {
      const { kind, seconds, done, total } = action.data;
      const prev = state.stepMetrics[kind];
      const doneVal = done ?? (prev ? prev.done + 1 : 1);
      const totalVal = total ?? (prev?.total ?? 0);
      const prevAvg = prev?.avgSeconds ?? seconds;
      const newAvg = prev ? 0.4 * seconds + 0.6 * prevAvg : seconds;
      return {
        ...state,
        stepMetrics: {
          ...state.stepMetrics,
          [kind]: { avgSeconds: newAvg, done: doneVal, total: totalVal },
        },
      };
    }
    case 'bridge/set_current_file':
      return {
        ...state,
        structuralVersion: state.structuralVersion + 1,
        appState: 'processing',
        currentPhase: '',
        activeProgress: 0,
        stepMetrics: { chunks: null, macro: null, boundary: null },
        files: state.files.map(file =>
          file.id === action.data.id
            ? { ...file, status: 'processing', progress: 0, phase: 1, phaseText: undefined, errorText: undefined }
            : file,
        ),
      };
    case 'bridge/file_done':
      return {
        ...state,
        structuralVersion: state.structuralVersion + 1,
        activeProgress: 0,
        files: state.files.map(file =>
          file.id === action.data.id
            ? {
                ...file,
                status: 'done',
                progress: 100,
                phase: 3,
                outputHtml: action.data.output_html,
                outputDir: action.data.output_dir,
                phaseText: undefined,
                errorText: undefined,
                completedAt: Date.now(),
              }
            : file,
        ),
      };
    case 'bridge/file_failed':
      return {
        ...state,
        structuralVersion: state.structuralVersion + 1,
        files: state.files.map(file =>
          file.id === action.data.id
            ? {
                ...file,
                status: 'error',
                progress: 0,
                phase: 0,
                phaseText: 'Errore',
                errorText: action.data.error || 'Elaborazione non completata.',
              }
            : file,
        ),
      };
    default:
      return state;
  }
}
