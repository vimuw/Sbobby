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
};

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

export type ProcessingState = {
  files: FileItem[];
  appState: AppStatus;
  currentPhase: string;
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
};

export type ProcessingAction =
  | { type: 'queue/add'; files: FileItem[] }
  | { type: 'queue/remove'; id: string }
  | { type: 'queue/move'; id: string; direction: 'up' | 'down' }
  | { type: 'queue/update_source'; id: string; path?: string; name?: string; size?: number; duration?: number }
  | { type: 'queue/clear_completed' }
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
  appState: 'idle',
  currentPhase: '',
  workTotals: { chunks: 0, macro: 0, boundary: 0 },
  workDone: { chunks: 0, macro: 0, boundary: 0 },
};

export function processingReducer(state: ProcessingState, action: ProcessingAction): ProcessingState {
  switch (action.type) {
    case 'queue/add':
      return { ...state, files: [...state.files, ...action.files] };
    case 'queue/remove':
      return { ...state, files: state.files.filter(file => file.id !== action.id) };
    case 'queue/move': {
      const idx = state.files.findIndex(file => file.id === action.id);
      if (idx < 0) return state;
      const nextIdx = action.direction === 'up' ? idx - 1 : idx + 1;
      if (nextIdx < 0 || nextIdx >= state.files.length) return state;
      const files = [...state.files];
      [files[idx], files[nextIdx]] = [files[nextIdx], files[idx]];
      return { ...state, files };
    }
    case 'queue/update_source':
      return {
        ...state,
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
      return { ...state, files: state.files.filter(file => file.status !== 'done') };
    case 'queue/clear_all':
      return { ...state, files: [] };
    case 'app/set_status':
      return { ...state, appState: action.status };
    case 'bridge/update_progress':
      return {
        ...state,
        files: state.files.map(file =>
          file.status === 'processing'
            ? { ...file, progress: Math.round(action.value * 100) }
            : file,
        ),
      };
    case 'bridge/update_phase':
      return { ...state, currentPhase: action.text };
    case 'bridge/process_done':
      return {
        ...state,
        appState: 'idle',
        currentPhase: '',
        workTotals: action.data?.cancelled ? { chunks: 0, macro: 0, boundary: 0 } : state.workTotals,
        workDone: action.data?.cancelled ? { chunks: 0, macro: 0, boundary: 0 } : state.workDone,
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
    case 'bridge/register_step_time':
      return state;
    case 'bridge/set_current_file':
      return {
        ...state,
        appState: 'processing',
        currentPhase: '',
        files: state.files.map(file =>
          file.id === action.data.id
            ? { ...file, status: 'processing', progress: 0, phase: 1, phaseText: undefined, errorText: undefined }
            : file,
        ),
      };
    case 'bridge/file_done':
      return {
        ...state,
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
              }
            : file,
        ),
      };
    case 'bridge/file_failed':
      return {
        ...state,
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
