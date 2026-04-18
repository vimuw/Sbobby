import type { Dispatch } from 'react';
import type {
  FileDescriptor,
  FileDonePayload,
  FileFailedPayload,
  ProcessDonePayload,
  ProcessingAction,
  SetCurrentFilePayload,
  StepTimePayload,
  WorkDonePayload,
  WorkTotalsPayload,
} from './appState';

export interface ValidationCheck {
  id: string;
  label: string;
  status: 'ok' | 'warning' | 'error';
  message: string;
  details?: string;
}

export interface ValidationResult {
  ok: boolean;
  summary: string;
  checks: ValidationCheck[];
}

export interface ModelOption {
  id: string;
  label: string;
  summary: string;
  default_chunk_minutes: number;
  phase1_temperature?: number;
}

export interface ArchiveSession {
  name: string;
  completed_at_iso: string;
  html_path: string;
  effective_model: string;
  input_path: string;
  session_dir: string;
}

export type ElSbobinatorBridge = BridgeCallbacks | null;

export interface BridgeCallbacks {
  appendConsole: (msg: string) => void;
  updateProgress: (value: number) => void;
  updatePhase: (text: string) => void;
  updateModel: (model: string) => void;
  processDone: (data: ProcessDonePayload) => void;
  setWorkTotals: (data: WorkTotalsPayload) => void;
  updateWorkDone: (data: WorkDonePayload) => void;
  registerStepTime: (data: StepTimePayload) => void;
  setCurrentFile: (data: SetCurrentFilePayload) => void;
  fileDone: (data: FileDonePayload) => void;
  fileFailed: (data: FileFailedPayload) => void;
  askRegenerate: (data: { filename: string; mode?: 'completed' | 'resume' }) => void;
  askNewKey: () => void;
  filesDropped: (files: FileDescriptor[]) => void;
}

export interface PywebviewApi {
  load_settings?: () => Promise<{
    api_key?: string;
    fallback_keys?: string[];
    preferred_model?: string;
    fallback_models?: string[];
    available_models?: ModelOption[];
    has_protected_key?: boolean;
  }>;
  save_settings?: (
    apiKey: string | null,
    fallbackKeys: string[],
    preferredModel: string,
    fallbackModels: string[],
  ) => Promise<{ ok: boolean; error?: string }>;
  ask_files?: () => Promise<FileDescriptor[]>;
  ask_media_file?: () => Promise<FileDescriptor | null>;
  check_path_exists?: (path: string) => Promise<{ ok: boolean; exists: boolean }>;
  collect_dropped_files?: (names: string[]) => Promise<{ ok: boolean }>;
  start_processing?: (files: FileDescriptor[], apiKey: string, resumeSession: boolean, preferredModel: string, fallbackModels: string[]) => Promise<{ ok: boolean; error?: string }>;
  stop_processing?: () => Promise<{ ok: boolean }>;
  answer_regenerate?: (regenerate: boolean | null) => Promise<{ ok: boolean }>;
  answer_new_key?: (key: string) => Promise<{ ok: boolean }>;
  open_file?: (path: string) => Promise<{ ok: boolean; error?: string }>;
  open_url?: (url: string) => Promise<{ ok: boolean; error?: string }>;
  read_html_content?: (path: string) => Promise<{ ok: boolean; content?: string; error?: string }>;
  save_html_content?: (path: string, content: string, generation?: number) => Promise<{ ok: boolean; error?: string }>;
  stream_media_file?: (path: string) => Promise<{ ok: boolean; url?: string; error?: string }>;
  export_docx?: (filename: string, docxHtml: string) => Promise<{ ok: boolean; error?: string }>;
  show_notification?: (title: string, message: string) => Promise<void>;
  validate_environment?: (
    apiKey?: string,
    checkApiKey?: boolean,
    preferredModel?: string,
    fallbackModels?: string[],
  ) => Promise<{ ok: boolean; result?: ValidationResult; error?: string }>;
  get_session_storage_info?: () => Promise<{ ok: boolean; total_bytes?: number; total_sessions?: number; error?: string }>;
  cleanup_old_sessions?: (maxAgeDays?: number) => Promise<{ ok: boolean; removed?: number; freed_bytes?: number; errors?: number; error?: string }>;
  get_completed_sessions?: (limit?: number) => Promise<{ ok: boolean; sessions?: ArchiveSession[]; error?: string }>;
  delete_session?: (sessionDir: string) => Promise<{ ok: boolean; error?: string }>;
  update_session_input_path?: (sessionDir: string, newPath: string) => Promise<{ ok: boolean; error?: string }>;
  open_session_folder?: () => Promise<{ ok: boolean; error?: string }>;
  download_and_install_update?: (version: string) => Promise<{ ok: boolean; error?: string }>;
}

export function createBridge(options: {
  dispatch: Dispatch<ProcessingAction>;
  appendConsole: (msg: string) => void;
  onRegenerate: (data: { filename: string; mode?: 'completed' | 'resume' }) => void;
  onAskNewKey: () => void;
  onBatchDone: (data: ProcessDonePayload) => void;
  onFileDone: (data: FileDonePayload) => void;
  onFilesDropped: (files: FileDescriptor[]) => void;
}): BridgeCallbacks {
  const { dispatch, appendConsole, onRegenerate, onAskNewKey, onBatchDone, onFileDone, onFilesDropped } = options;

  return {
    appendConsole,
    updateProgress: value => dispatch({ type: 'bridge/update_progress', value }),
    updatePhase: text => dispatch({ type: 'bridge/update_phase', text }),
    updateModel: model => dispatch({ type: 'bridge/update_model', model }),
    processDone: data => {
      dispatch({ type: 'bridge/process_done', data });
      onBatchDone(data);
    },
    setWorkTotals: data => dispatch({ type: 'bridge/set_work_totals', data }),
    updateWorkDone: data => dispatch({ type: 'bridge/update_work_done', data }),
    registerStepTime: data => dispatch({ type: 'bridge/register_step_time', data }),
    setCurrentFile: data => dispatch({ type: 'bridge/set_current_file', data }),
    fileDone: data => {
      dispatch({ type: 'bridge/file_done', data });
      onFileDone(data);
    },
    fileFailed: data => dispatch({ type: 'bridge/file_failed', data }),
    askRegenerate: onRegenerate,
    askNewKey: onAskNewKey,
    filesDropped: onFilesDropped,
  };
}
