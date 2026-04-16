import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { motion, AnimatePresence } from 'motion/react';
import {
  AlertTriangle,
  Check,
  CheckCircle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Copy,
  Eye,
  EyeOff,
  ExternalLink,
  FileAudio,
  FolderOpen,
  Github,
  History,
  Key,
  ListOrdered,
  Moon,
  Play,
  Search,
  Settings,
  Square,
  Sun,
  Terminal,
  Trash2,
  UploadCloud,
  X,
  Zap,
} from 'lucide-react';
import { GITHUB_RELEASES_URL, GITHUB_URL, KOFI_URL } from './branding';
import { type ArchiveSession, type ElSbobinatorBridge, type PywebviewApi } from './bridge';
import { getDoneFiles, getPendingFiles, initialProcessingState, isSuccessfulProcessDone, processingReducer, type AppStatus, type FileDescriptor, type FileItem, type ProcessDonePayload } from './appState';
import { formatRelativeTime, GEMINI_KEY_PATTERN, shortModelName } from './utils';
import { useConsole } from './hooks/useConsole';
import { useTheme } from './hooks/useTheme';
import { useUpdateChecker } from './hooks/useUpdateChecker';
import { useQueuePersistence } from './hooks/useQueuePersistence';
import { useApiReady } from './hooks/useApiReady';
import { useBridgeCallbacks } from './hooks/useBridgeCallbacks';
import { useBodyScrollLock } from './hooks/useBodyScrollLock';
import { CompletedFileCard, QueueFileCard } from './components/QueueFileCard';
import { ProcessingStatusBanner } from './components/ProcessingStatusBanner';
import { RegenerateModal } from './components/modals/RegenerateModal';
import { NewKeyModal } from './components/modals/NewKeyModal';
import { SettingsModal } from './components/modals/SettingsModal';
import { ConfirmActionModal } from './components/modals/ConfirmActionModal';
import { DuplicateFileModal, type AlreadyProcessedMatch, type DuplicatePrompt } from './components/modals/DuplicateFileModal';
import { buildArchiveLookup, filterArchiveSessionsByInputPath, getArchiveMatchesForFile } from './duplicateDetection';
import { loadEditorSession, saveEditorSession, type EditorSession } from './editorSessions';
import { normalizePreviewHtmlContent } from './previewHtml';
const PreviewModal = React.lazy(() => import('./components/modals/PreviewModal').then(m => ({ default: m.PreviewModal })));

declare global {
  interface Window {
    pywebview: { api?: PywebviewApi };
    elSbobinatorBridge: ElSbobinatorBridge;
  }
}

type PreviewState = {
  content: string | null;
  title: string;
  path: string;
  audioSrc: string | null;
  fileId: string | null;
  sourcePath: string;
  audioRelinkNeeded: boolean;
  initAudio: { time?: number; playbackRate?: number; volume?: number };
  initScrollTop?: number;
};

type WebViewHostWindow = Window & {
  chrome?: {
    webview?: {
      postMessageWithAdditionalObjects?: (message: string, additionalObjects: FileList) => void;
    };
  };
};

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

const initialPreviewState: PreviewState = {
  content: null,
  title: '',
  path: '',
  audioSrc: null,
  fileId: null,
  sourcePath: '',
  audioRelinkNeeded: false,
  initAudio: {},
  initScrollTop: undefined,
};

type UiMode = 'setup' | 'ready-empty' | 'ready-with-files' | 'processing' | 'canceling';
type ConfirmActionState =
  | { type: 'stop-processing' }
  | { type: 'remove-file'; fileId: string; fileName: string }
  | { type: 'clear-completed'; count: number }
  | { type: 'delete-archive-session'; sessionDir: string; name: string };

const ARCHIVE_PAGE_SIZE = 5;

type PendingArchiveReplacement = {
  fileName: string;
  inputPath?: string;
  sessions: ArchiveSession[];
};

export default function App() {
  const [{ files, structuralVersion, appState, currentPhase, currentModel, activeProgress, workTotals, workDone }, dispatch] = useReducer(processingReducer, initialProcessingState);

  // --- Extracted hooks ---
  const { consoleLogs, appendConsole } = useConsole();
  const { themeMode, setThemeMode } = useTheme();
  const { updateAvailable, dismissUpdate } = useUpdateChecker();
  const {
    apiReady,
    bridgeDelayed,
    apiKey,
    setApiKey,
    fallbackKeys,
    setFallbackKeys,
    preferredModel,
    setPreferredModel,
    fallbackModels,
    setFallbackModels,
    availableModels,
  } = useApiReady(appendConsole);

  // --- Modal state ---
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [regeneratePrompt, setRegeneratePrompt] = useState<{ filename: string; mode?: 'completed' | 'resume' } | null>(null);
  const [askNewKeyPrompt, setAskNewKeyPrompt] = useState(false);
  const [confirmAction, setConfirmAction] = useState<ConfirmActionState | null>(null);
  const [duplicatePrompt, setDuplicatePrompt] = useState<DuplicatePrompt>(null);

  // --- Preview state ---
  const [preview, setPreview] = useState<PreviewState>(initialPreviewState);

  // --- UI state ---
  const [isDragging, setIsDragging] = useState(false);
  const [showConsole, setShowConsole] = useState(() => localStorage.getItem('show_console') === 'true');
  const [isConsoleExpanded, setIsConsoleExpanded] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const [completedSearch, setCompletedSearch] = useState('');
  const [setupKeyInput, setSetupKeyInput] = useState('');
  const [setupKeyShowRaw, setSetupKeyShowRaw] = useState(false);
  const [setupKeySaving, setSetupKeySaving] = useState(false);
  const [setupKeyError, setSetupKeyError] = useState<string | null>(null);
  const [archiveSessions, setArchiveSessions] = useState<ArchiveSession[]>([]);
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const [archiveSearch, setArchiveSearch] = useState('');
  const [archiveSort, setArchiveSort] = useState<'newest' | 'oldest'>('newest');
  const [archivePage, setArchivePage] = useState(0);
  const [isPeakHour, setIsPeakHour] = useState(() => { const h = new Date().getHours(); return h >= 15 && h < 20; });
  const [isPeakDismissed, setIsPeakDismissed] = useState(() => {
    const ts = localStorage.getItem('peakBannerDismissedUntil');
    return ts ? Date.now() < Number(ts) : false;
  });
  const [autoContinue, setAutoContinue] = useState(() => localStorage.getItem('auto_continue') !== 'false');
  const [batchTotal, setBatchTotal] = useState(0);
  const [batchCompleted, setBatchCompleted] = useState(0);
  const [completionFlash, setCompletionFlash] = useState(false);

  // --- Refs ---
  const fileInputRef = useRef<HTMLInputElement>(null);
  const filesRef = useRef<FileItem[]>([]);
  const appStateRef = useRef<AppStatus>('idle');
  const currentEditorSessionRef = useRef<EditorSession>({});
  const currentPreviewSessionKeyRef = useRef<string | null>(null);
  const consoleScrollRef = useRef<HTMLDivElement>(null);
  const isMouseInConsoleRef = useRef(false);
  const archivePanelRef = useRef<HTMLDivElement>(null);
  const autoContinueRef = useRef(autoContinue);
  const startProcessingRef = useRef<(isContinuation?: boolean) => Promise<boolean>>(async () => false);

  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  useEffect(() => {
    appStateRef.current = appState;
  }, [appState]);

  autoContinueRef.current = autoContinue;

  useEffect(() => {
    localStorage.setItem('auto_continue', String(autoContinue));
  }, [autoContinue]);

  useEffect(() => {
    if (!isConsoleExpanded || isMouseInConsoleRef.current) return;
    const el = consoleScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [consoleLogs, isConsoleExpanded]);

  // --- Flush editor session on app close ---
  useEffect(() => {
    const handleBeforeUnload = () => {
      const sessionKey = currentPreviewSessionKeyRef.current;
      if (!sessionKey) return;
      const session = currentEditorSessionRef.current;
      const hasData = session.audioTime !== undefined
        || session.playbackRate !== undefined
        || session.volume !== undefined
        || session.scrollTop !== undefined;
      if (hasData) saveEditorSession(sessionKey, session);
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, []);

  // --- Archive ref (kept in sync for stable callbacks) ---
  const archiveSessionsRef = useRef<typeof archiveSessions>([]);
  archiveSessionsRef.current = archiveSessions;
  const pendingArchiveReplacementsRef = useRef<Map<string, PendingArchiveReplacement>>(new Map());
  const archiveReplacementCleanupInFlightRef = useRef<Set<string>>(new Set());

  const refreshArchiveSessions = useCallback(async () => {
    try {
      const result = await window.pywebview?.api?.get_completed_sessions?.();
      if (result?.ok && result.sessions) setArchiveSessions(result.sessions);
    } catch {}
  }, []);

  const finalizeArchiveReplacement = useCallback(async (fileId: string) => {
    const pendingReplacement = pendingArchiveReplacementsRef.current.get(fileId);
    if (!pendingReplacement || archiveReplacementCleanupInFlightRef.current.has(fileId)) return;

    archiveReplacementCleanupInFlightRef.current.add(fileId);
    const deletedSessionDirs: string[] = [];
    const currentFile = filesRef.current.find(file => file.id === fileId);
    const deletableSessions = filterArchiveSessionsByInputPath(
      currentFile?.path ?? pendingReplacement.inputPath,
      pendingReplacement.sessions,
    );

    try {
      for (const session of deletableSessions) {
        try {
          const res = await window.pywebview?.api?.delete_session?.(session.session_dir);
          if (res?.ok) {
            deletedSessionDirs.push(session.session_dir);
          } else {
            appendConsole(`❌ Errore eliminazione sessione archiviata per ${pendingReplacement.fileName}: ${res?.error ?? 'errore sconosciuto'}`);
          }
        } catch (error) {
          appendConsole(`❌ Errore eliminazione sessione archiviata per ${pendingReplacement.fileName}: ${getErrorMessage(error)}`);
        }
      }

      if (deletedSessionDirs.length > 0) {
        const deletedSessionDirSet = new Set(deletedSessionDirs);
        setArchiveSessions(prev => prev.filter(session => !deletedSessionDirSet.has(session.session_dir)));
      }

      if (deletedSessionDirs.length !== deletableSessions.length) {
        await refreshArchiveSessions();
      }
    } finally {
      pendingArchiveReplacementsRef.current.delete(fileId);
      archiveReplacementCleanupInFlightRef.current.delete(fileId);
    }
  }, [appendConsole, refreshArchiveSessions]);

  // --- Queue persistence ---
  useQueuePersistence(files, structuralVersion, dispatch, appendConsole);

  // --- Archive fetch ---
  useEffect(() => {
    if (!apiReady) return;
    void refreshArchiveSessions();
  }, [apiReady, refreshArchiveSessions]);

  useEffect(() => {
    const currentFileIds = new Set(files.map(file => file.id));

    for (const fileId of pendingArchiveReplacementsRef.current.keys()) {
      if (!currentFileIds.has(fileId)) {
        pendingArchiveReplacementsRef.current.delete(fileId);
        archiveReplacementCleanupInFlightRef.current.delete(fileId);
      }
    }

    for (const file of files) {
      if (file.status === 'done' && pendingArchiveReplacementsRef.current.has(file.id)) {
        void finalizeArchiveReplacement(file.id);
      }
    }
  }, [files, finalizeArchiveReplacement]);

  // --- File deduplication ---
  const getFileFingerprint = useCallback((file: Pick<FileItem, 'path' | 'name' | 'size' | 'duration'>) => {
    const normalizedPath = String(file.path || '').trim().toLowerCase();
    if (normalizedPath) return `path:${normalizedPath}`;
    return `meta:${String(file.name || '').trim().toLowerCase()}::${Number(file.size || 0)}::${Math.round(Number(file.duration || 0))}`;
  }, []);

  const enqueueUniqueFiles = useCallback((incomingFiles: FileItem[]) => {
    if (incomingFiles.length === 0) return;

    const currentFiles = filesRef.current;
    const currentArchive = archiveSessionsRef.current;

    // Build lookup maps for fast duplicate detection
    const pendingFingerprints = new Set(
      currentFiles.filter(f => f.status !== 'done').map(f => getFileFingerprint(f)),
    );
    const doneByFingerprint = new Map(
      currentFiles.filter(f => f.status === 'done').map(f => [getFileFingerprint(f), f]),
    );
    const archiveLookup = buildArchiveLookup(currentArchive);

    const uniqueFiles: FileItem[] = [];
    const inQueueNames: string[] = [];
    const alreadyProcessedMatches: AlreadyProcessedMatch[] = [];
    // Track fingerprints seen within this batch to handle multi-file drops
    const seenInBatch = new Set<string>();

    for (const file of incomingFiles) {
      const fp = getFileFingerprint(file);

      if (pendingFingerprints.has(fp) || seenInBatch.has(fp)) {
        inQueueNames.push(file.name);
      } else if (doneByFingerprint.has(fp)) {
        alreadyProcessedMatches.push({ source: 'done', existingFile: doneByFingerprint.get(fp)!, incoming: file });
        seenInBatch.add(fp);
      } else {
        const archiveMatches = getArchiveMatchesForFile(file, archiveLookup);
        if (archiveMatches.length > 0) {
          alreadyProcessedMatches.push({ source: 'archive', sessions: archiveMatches, incoming: file });
          seenInBatch.add(fp);
        } else {
          seenInBatch.add(fp);
          uniqueFiles.push(file);
        }
      }
    }

    if (uniqueFiles.length > 0) dispatch({ type: 'queue/add', files: uniqueFiles });

    // Show modal for the most actionable conflict type; prefer already-processed over in-queue
    if (alreadyProcessedMatches.length > 0) {
      setDuplicatePrompt({ kind: 'already-processed', matches: alreadyProcessedMatches, alsoInQueue: inQueueNames.length > 0 ? inQueueNames : undefined });
    } else if (inQueueNames.length > 0) {
      setDuplicatePrompt({ kind: 'in-queue', filenames: inQueueNames });
    }
  }, [dispatch, getFileFingerprint]);

  const onFileContinued = useCallback(() => { setBatchCompleted(prev => prev + 1); }, []);
  const onBatchReset = useCallback(() => {
    setBatchTotal(0);
    setBatchCompleted(0);
  }, []);
  const onBatchFullyDone = useCallback((data: ProcessDonePayload) => {
    onBatchReset();
    if (isSuccessfulProcessDone(data)) {
      setCompletionFlash(true);
      setTimeout(() => setCompletionFlash(false), 5000);
    }
  }, [onBatchReset]);

  useEffect(() => {
    if (appState === 'processing') setCompletionFlash(false);
  }, [appState]);

  // --- Bridge callbacks ---
  useBridgeCallbacks({ dispatch, appendConsole, filesRef, appStateRef, enqueueUniqueFiles, setRegeneratePrompt, setAskNewKeyPrompt, autoContinueRef, startProcessingRef, onFileContinued, onBatchReset, onBatchFullyDone });

  // --- Body scroll lock ---
  const isModalOpen = isSettingsOpen || regeneratePrompt !== null || preview.content !== null || askNewKeyPrompt || confirmAction !== null || duplicatePrompt !== null;
  useBodyScrollLock(isModalOpen);

  // --- Handlers ---
  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); if (appState === 'idle') setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (appStateRef.current !== 'idle' || !e.dataTransfer.files.length) return;
    const w = window as WebViewHostWindow;
    if (w.chrome?.webview?.postMessageWithAdditionalObjects) {
      const names = Array.from(e.dataTransfer.files).map((f: File) => f.name);
      w.chrome.webview.postMessageWithAdditionalObjects('FilesDropped', e.dataTransfer.files);
      window.pywebview?.api?.collect_dropped_files?.(names);
    }
  };

  const handleBrowseClick = async () => {
    if (appState !== 'idle') return;
    if (!apiReady || !window.pywebview || !window.pywebview.api) {
      appendConsole('⚠ In attesa della connessione con Python... riprova tra un momento.');
      return;
    }
    try {
      const selectedFiles = await window.pywebview.api.ask_files?.();
      if (selectedFiles?.length > 0) {
        const filesToAdd: FileItem[] = selectedFiles.map((f: FileDescriptor) => ({
          id: crypto.randomUUID(), name: f.name, size: f.size, duration: f.duration || 0,
          path: f.path, status: 'queued' as const, progress: 0, phase: 0,
        }));
        enqueueUniqueFiles(filesToAdd);
      }
    } catch (e) { appendConsole(`❌ Errore selezione file: ${e}`); }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      const filesToAdd: FileItem[] = Array.from(e.target.files).map((file: File) => ({
        id: crypto.randomUUID(), name: file.name, size: file.size, duration: 0,
        status: 'queued' as const, progress: 0, phase: 0,
      }));
      enqueueUniqueFiles(filesToAdd);
      e.target.value = '';
    }
  };

  const requestRemoveFile = useCallback((id: string) => {
    const targetFile = filesRef.current.find(file => file.id === id);
    if (!targetFile) return;
    if (appState !== 'idle' && targetFile.status !== 'done') return;
    setConfirmAction({ type: 'remove-file', fileId: id, fileName: targetFile.name });
  }, [appState]);

  const dndSensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id || appState !== 'idle') return;
    const fromIndex = files.findIndex(f => f.id === active.id);
    const toIndex = files.findIndex(f => f.id === over.id);
    if (fromIndex < 0 || toIndex < 0) return;
    dispatch({ type: 'queue/reorder', fromIndex, toIndex });
  }, [appState, files]);


  const resolveQueuedFilesForProcessing = useCallback(async () => {
    const api = window.pywebview?.api;
    const queuedFiles = filesRef.current.filter(file => file.status === 'queued');
    if (queuedFiles.length === 0) return [] as FileDescriptor[];
    const file = queuedFiles[0];
    const p = String(file.path || '').trim();
    const exists = p && api?.check_path_exists ? Boolean((await api.check_path_exists(p))?.exists) : Boolean(p);
    let nextPath = p;
    let nextName = file.name;
    let nextSize = file.size;
    let nextDuration = file.duration;
    if (!exists) {
      if (!api?.ask_media_file) { appendConsole(`Impossibile ricollegare l'audio per ${file.name}.`); return []; }
      appendConsole(`Audio non trovato per ${file.name}. Selezionalo di nuovo per continuare.`);
      const selectedFile = await api.ask_media_file();
      if (!selectedFile?.path) { appendConsole(`Avvio annullato: audio non ricollegato per ${file.name}.`); return []; }
      nextPath = selectedFile.path; nextName = selectedFile.name; nextSize = selectedFile.size; nextDuration = selectedFile.duration || 0;
      dispatch({ type: 'queue/update_source', id: file.id, path: nextPath, name: nextName, size: nextSize, duration: nextDuration });
      appendConsole(`Audio ricollegato: ${nextName}`);
    }
    return [{
      id: file.id,
      path: nextPath,
      name: nextName,
      size: nextSize,
      duration: nextDuration,
      resume_session: file.resumeSession,
    }] as FileDescriptor[];
  }, [appendConsole, dispatch]);

  const startProcessing = async (isContinuation: boolean = false) => {
    const currentQueued = filesRef.current.filter(f => f.status === 'queued');
    if (currentQueued.length === 0 || !apiKey.trim()) return false;
    if (isContinuation && appStateRef.current === 'canceling') return false;
    if (!window.pywebview?.api) return false;

    if (!isContinuation) {
      setBatchTotal(currentQueued.length);
      setBatchCompleted(0);
    }

    try {
      const fileDescriptors = await resolveQueuedFilesForProcessing();
      if (!fileDescriptors || fileDescriptors.length === 0) {
        return false;
      }

      const result = await window.pywebview.api.start_processing?.(fileDescriptors, apiKey.trim(), true, preferredModel, fallbackModels);
      if (!result?.ok) {
        appendConsole(`❌ ${result?.error || "Impossibile avviare l'elaborazione."}`);
        return false;
      }

      dispatch({ type: 'app/set_status', status: 'processing' });
      return true;
    } catch (e: unknown) {
      appendConsole(`❌ Errore avvio: ${getErrorMessage(e)}`);
      return false;
    }
  };

  startProcessingRef.current = startProcessing;

  const confirmStopProcessing = useCallback(async () => {
    setConfirmAction(null);
    dispatch({ type: 'app/set_status', status: 'canceling' });
    appendConsole('[!] Annullamento in corso, attendere prego...');
    if (window.pywebview?.api) await window.pywebview.api.stop_processing?.();
  }, [appendConsole]);

  const confirmClearCompleted = useCallback(() => {
    setConfirmAction(null);
    dispatch({ type: 'queue/clear_completed' });
    setCompletedSearch('');
    void refreshArchiveSessions();
  }, [refreshArchiveSessions]);

  const handleConfirmAction = useCallback(() => {
    if (!confirmAction) return;
    if (confirmAction.type === 'stop-processing') {
      void confirmStopProcessing();
      return;
    }
    if (confirmAction.type === 'remove-file') {
      const removedFile = filesRef.current.find(f => f.id === confirmAction.fileId);
      dispatch({ type: 'queue/remove', id: confirmAction.fileId });
      setConfirmAction(null);
      if (removedFile?.status === 'done') {
        void refreshArchiveSessions();
      }
      return;
    }
    if (confirmAction.type === 'delete-archive-session') {
      const { sessionDir } = confirmAction;
      setConfirmAction(null);
      window.pywebview?.api?.delete_session?.(sessionDir).then(res => {
        if (res?.ok) {
          setArchiveSessions(prev => prev.filter(s => s.session_dir !== sessionDir));
        } else {
          appendConsole(`❌ Errore eliminazione sessione: ${res?.error ?? 'errore sconosciuto'}`);
        }
      }).catch((e: unknown) => {
        appendConsole(`❌ Errore eliminazione sessione: ${getErrorMessage(e)}`);
      });
      return;
    }
    confirmClearCompleted();
  }, [confirmAction, confirmClearCompleted, confirmStopProcessing, appendConsole, refreshArchiveSessions]);

  const handleDuplicateAddAgain = useCallback(async (matches: AlreadyProcessedMatch[]) => {
    setDuplicatePrompt(null);
    for (const match of matches) {
      const replacementId = crypto.randomUUID();
      if (match.source === 'done') {
        const archiveMatches = filterArchiveSessionsByInputPath(
          match.incoming.path ?? match.existingFile.path,
          archiveSessionsRef.current,
        );
        if (archiveMatches.length > 0) {
          pendingArchiveReplacementsRef.current.set(replacementId, {
            fileName: match.incoming.name,
            inputPath: match.incoming.path,
            sessions: archiveMatches,
          });
        }
        dispatch({ type: 'queue/remove', id: match.existingFile.id });
        dispatch({ type: 'queue/add', files: [{ ...match.incoming, id: replacementId, resumeSession: false }] });
      } else {
        pendingArchiveReplacementsRef.current.set(replacementId, {
          fileName: match.incoming.name,
          inputPath: match.incoming.path,
          sessions: match.sessions,
        });
        dispatch({ type: 'queue/add', files: [{ ...match.incoming, id: replacementId, resumeSession: false }] });
      }
    }
  }, [dispatch]);

  const handleRegenerateAnswer = async (ans: boolean | null) => {
    setRegeneratePrompt(null);
    try {
      if (window.pywebview?.api?.answer_regenerate) await window.pywebview.api.answer_regenerate(ans);
    } catch (e) { console.error('Failed to send answer to Python:', e); }
  };

  const loadPreviewAudio = useCallback(async (sourcePath?: string) => {
    const normalizedSource = String(sourcePath || '').trim();
    if (!normalizedSource || !window.pywebview?.api?.stream_media_file) {
      setPreview(prev => ({ ...prev, audioSrc: null, audioRelinkNeeded: Boolean(normalizedSource) }));
      return;
    }
    const streamRes = await window.pywebview.api.stream_media_file(normalizedSource);
    if (streamRes.ok && streamRes.url) { setPreview(prev => ({ ...prev, audioSrc: streamRes.url, audioRelinkNeeded: false })); return; }
    setPreview(prev => ({ ...prev, audioSrc: null, audioRelinkNeeded: true }));
  }, []);

  const relinkPreviewAudio = useCallback(async () => {
    if (!window.pywebview?.api?.ask_media_file) return;
    try {
      const selectedFile = await window.pywebview.api.ask_media_file();
      if (!selectedFile?.path) return;
      if (preview.fileId) {
        dispatch({ type: 'queue/update_source', id: preview.fileId, path: selectedFile.path, name: selectedFile.name, size: selectedFile.size, duration: selectedFile.duration });
      }
      setPreview(prev => ({ ...prev, sourcePath: selectedFile.path }));
      await loadPreviewAudio(selectedFile.path);
      appendConsole(`Audio ricollegato: ${selectedFile.name}`);
    } catch (error: unknown) { appendConsole(`❌ Impossibile ricollegare l'audio: ${getErrorMessage(error)}`); }
  }, [appendConsole, loadPreviewAudio, preview.fileId]);

  const openPreview = useCallback(async (htmlPath: string, filename: string, sourcePath?: string, fileId?: string) => {
    if (window.pywebview?.api?.read_html_content) {
      appendConsole('Caricamento anteprima in corso...');
      try {
        const res = await window.pywebview.api.read_html_content(htmlPath);
        if (res.ok) {
          const bodyMatch = res.content.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
          const extractedContent = bodyMatch ? bodyMatch[1] : res.content.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
          const safeContent = normalizePreviewHtmlContent(extractedContent);
          const sessionKey = fileId ?? htmlPath;
          currentPreviewSessionKeyRef.current = sessionKey;
          const savedSession = loadEditorSession(sessionKey);
          currentEditorSessionRef.current = { ...savedSession };
          setPreview({
            content: safeContent,
            title: filename,
            path: htmlPath,
            fileId: fileId ?? null,
            sourcePath: sourcePath || '',
            audioSrc: null,
            audioRelinkNeeded: false,
            initAudio: { time: savedSession.audioTime, playbackRate: savedSession.playbackRate, volume: savedSession.volume },
            initScrollTop: savedSession.scrollTop,
          });
          await loadPreviewAudio(sourcePath);
        } else { appendConsole(`❌ Errore anteprima: ${res.error}`); }
      } catch (e: unknown) { appendConsole(`❌ Errore JS anteprima: ${getErrorMessage(e)}`); }
    } else { appendConsole('❌ Funzione anteprima non disponibile in questa versione.'); }
  }, [appendConsole, loadPreviewAudio]);

  const closePreview = useCallback(() => {
    const sessionKey = currentPreviewSessionKeyRef.current;
    if (sessionKey) {
      const session = currentEditorSessionRef.current;
      const hasData = session.audioTime !== undefined || session.playbackRate !== undefined || session.volume !== undefined || session.scrollTop !== undefined;
      if (hasData) saveEditorSession(sessionKey, session);
    }
    currentEditorSessionRef.current = {};
    currentPreviewSessionKeyRef.current = null;
    setPreview(initialPreviewState);
  }, []);

  useEffect(() => {
    if (appState !== 'processing' && confirmAction?.type === 'stop-processing') {
      setConfirmAction(null);
    }
  }, [appState, confirmAction]);

  const handleAudioStateChange = useCallback(({ currentTime, playbackRate, volume }: { currentTime: number; playbackRate: number; volume: number }) => {
    currentEditorSessionRef.current = { ...currentEditorSessionRef.current, audioTime: currentTime, playbackRate, volume };
  }, []);

  const handleScrollTopChange = useCallback((scrollTop: number) => {
    currentEditorSessionRef.current = { ...currentEditorSessionRef.current, scrollTop };
  }, []);

  const openFile = useCallback(async (path: string) => {
    if (!window.pywebview?.api) return;
    const res = await window.pywebview.api.open_file(path);
    if (res && !res.ok) appendConsole(`❌ Impossibile aprire il file: ${res.error ?? path}`);
  }, [appendConsole]);


  // --- Computed values ---
  const { queuedCount, processingCount } = useMemo(() => {
    let queuedCount = 0, processingCount = 0;
    for (const f of files) {
      if (f.status === 'queued') queuedCount++;
      else if (f.status === 'processing') processingCount++;
    }
    return { queuedCount, processingCount };
  }, [files]);
  const hasApiKey = Boolean(apiKey.trim());
  const isApiKeyValid = GEMINI_KEY_PATTERN.test(apiKey.trim());
  const canStart = queuedCount > 0 && hasApiKey && isApiKeyValid;
  const uiMode: UiMode =
    appState === 'canceling' ? 'canceling' :
    appState === 'processing' ? 'processing' :
    (!hasApiKey || !isApiKeyValid) ? 'setup' :
    queuedCount > 0 ? 'ready-with-files' : 'ready-empty';
  const lastConsoleMessage = consoleLogs.length > 0 ? consoleLogs[consoleLogs.length - 1] : 'Pronto per iniziare.';

  const handleSetupSave = useCallback(async () => {
    setSetupKeySaving(true);
    setSetupKeyError(null);
    try {
      if (!window.pywebview?.api?.save_settings) {
        const err = 'Bridge Python non disponibile — impostazioni non salvate.';
        setSetupKeyError(err);
        appendConsole(`❌ ${err}`);
        return;
      }
      let result;
      try {
        result = await window.pywebview.api.save_settings(setupKeyInput.trim(), fallbackKeys, preferredModel, fallbackModels);
      } catch (e: unknown) {
        const err = `Errore salvataggio: ${getErrorMessage(e)}`;
        setSetupKeyError(err);
        appendConsole(`❌ ${err}`);
        return;
      }
      if (!result?.ok) {
        const err = `Errore salvataggio: ${result?.error || 'errore sconosciuto'}`;
        setSetupKeyError(err);
        appendConsole(`❌ ${err}`);
        return;
      }
      setApiKey(setupKeyInput.trim());
    } finally {
      setSetupKeySaving(false);
    }
  }, [setupKeyInput, fallbackKeys, preferredModel, fallbackModels, appendConsole, setApiKey]);

  useEffect(() => {
    document.title = appState === 'processing' ? '⏳ El Sbobinator' : 'El Sbobinator';
  }, [appState]);

  useEffect(() => {
    const check = () => {
      const h = new Date().getHours();
      setIsPeakHour(h >= 15 && h < 20);
    };
    const id = setInterval(check, 60_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (isPeakHour) {
      const ts = localStorage.getItem('peakBannerDismissedUntil');
      setIsPeakDismissed(ts ? Date.now() < Number(ts) : false);
    }
  }, [isPeakHour]);

  const titleGradient = { background: 'linear-gradient(90deg, var(--gradient-title-from), var(--gradient-title-to))', WebkitBackgroundClip: 'text' as const, WebkitTextFillColor: 'transparent' };
  const sGradient = { background: 'linear-gradient(90deg, var(--gradient-s-from), var(--gradient-s-to))', WebkitBackgroundClip: 'text' as const, WebkitTextFillColor: 'transparent' };

  const pendingFiles = useMemo(() => getPendingFiles(files), [files]);
  const doneFiles = useMemo(() => getDoneFiles(files), [files]);
  const showProcessingBanner = appState === 'processing' || appState === 'canceling' || completionFlash;
  const bannerFile = files.find(f => f.status === 'processing') ?? (completionFlash ? doneFiles[0] : undefined);
  const filteredDoneFiles = useMemo(
    () => completedSearch.trim()
      ? doneFiles.filter(f => f.name.toLowerCase().includes(completedSearch.toLowerCase()))
      : doneFiles,
    [doneFiles, completedSearch],
  );
  const confirmModalCopy = useMemo(() => {
    if (!confirmAction) return null;
    if (confirmAction.type === 'stop-processing') {
      return {
        title: 'Interrompere la sbobinatura?',
        description: "Stai per fermare l'elaborazione in corso. Il processo verrà interrotto e il file attuale tornerà in coda. Vuoi continuare?",
        confirmLabel: 'Conferma stop',
        cancelLabel: 'Continua elaborazione',
      };
    }
    if (confirmAction.type === 'remove-file') {
      return {
        title: 'Rimuovere questo elemento?',
        description: `"${confirmAction.fileName}" verrà rimosso dalla lista. Vuoi continuare?`,
        confirmLabel: 'Conferma rimozione',
        cancelLabel: 'Tieni elemento',
      };
    }
    if (confirmAction.type === 'delete-archive-session') {
      return {
        title: 'Eliminare questa sbobina?',
        description: `"${confirmAction.name}" e tutti i suoi dati di sessione verranno eliminati definitivamente dal disco. L'operazione è irreversibile.`,
        confirmLabel: 'Elimina definitivamente',
        cancelLabel: 'Annulla',
      };
    }
    return {
      title: 'Pulire le sbobine completate?',
      description: confirmAction.count === 1
        ? "La sbobina completata verrà spostata nell'archivio e rimossa dalla lista. Vuoi continuare?"
        : `Le ${confirmAction.count} sbobine completate verranno spostate nell'archivio e rimosse dalla lista. Vuoi continuare?`,
      confirmLabel: 'Conferma pulizia',
      cancelLabel: 'Mantieni nella lista',
    };
  }, [confirmAction]);

  const archiveFiltered = useMemo(() => {
    const doneHtmlPaths = new Set(doneFiles.map(f => f.outputHtml).filter(Boolean));
    return archiveSessions.filter(s => !doneHtmlPaths.has(s.html_path));
  }, [archiveSessions, doneFiles]);

  const archiveDisplayed = useMemo(() => {
    const q = archiveSearch.trim().toLowerCase();
    const filtered = q ? archiveFiltered.filter(s => s.name.toLowerCase().includes(q)) : archiveFiltered;
    return [...filtered].sort((a, b) => {
      const ta = a.completed_at_iso ? new Date(a.completed_at_iso).getTime() : 0;
      const tb = b.completed_at_iso ? new Date(b.completed_at_iso).getTime() : 0;
      return archiveSort === 'newest' ? tb - ta : ta - tb;
    });
  }, [archiveFiltered, archiveSearch, archiveSort]);

  const archiveTotalPages = Math.ceil(archiveDisplayed.length / ARCHIVE_PAGE_SIZE);

  const archivePageData = useMemo(
    () => archiveDisplayed.slice(archivePage * ARCHIVE_PAGE_SIZE, (archivePage + 1) * ARCHIVE_PAGE_SIZE),
    [archiveDisplayed, archivePage],
  );

  useEffect(() => {
    setArchivePage(0);
  }, [archiveSearch, archiveSort, archiveFiltered]);

  useEffect(() => {
    if (!isArchiveOpen) return;
    setTimeout(() => archivePanelRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 50);
  }, [archivePage]); // eslint-disable-line react-hooks/exhaustive-deps

  const sortableIds = useMemo(() => pendingFiles.map(f => f.id), [pendingFiles]);

  return (
    <div className="app-shell min-h-screen font-sans flex flex-col" style={{ background: 'var(--bg-base)', color: 'var(--text-secondary)' }}>

      {/* Top Navigation */}
      <header className="sticky top-0 z-40 backdrop-blur-2xl" style={{ borderBottom: '1px solid var(--border-subtle)', background: 'rgba(16, 13, 11, 0.08)' }}>
        <div className="max-w-3xl mx-auto px-5 sm:px-6 min-h-[84px] flex items-center justify-between gap-4">
          <div className="flex items-center gap-1">
            <img src="./icon.png" alt="El Sbobinator" className="app-logo" draggable={false} />
            <h1 className="brand-mark text-[1.45rem] sm:text-[1.75rem] font-semibold flex items-baseline tracking-tight leading-none overflow-visible py-1">
              <span style={titleGradient}>El&nbsp;</span>
              <span className="relative inline-block mx-[2px] overflow-visible">
                <svg className="absolute -top-[10px] left-1/2 -translate-x-[42%] w-[22px] h-[32px] drop-shadow-md z-10 pointer-events-none" viewBox="0 0 32 50" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ transform: 'rotate(-10deg)' }}>
                  <path d="M 3 22 C 5 40, 12 48, 17 48 C 23 48, 28 38, 29 22" fill="none" stroke="#D19A3F" strokeWidth="1.5" strokeLinecap="round" />
                  <circle cx="17" cy="48" r="2" fill="#D96D42" />
                  <circle cx="17" cy="48" r="1" fill="#F5D57F" />
                  <path d="M 2 22 C 2 18, 30 18, 30 22" fill="#C38243"/>
                  <path d="M 9 18 C 9 18, 11 4, 16 4 C 21 4, 23 18, 23 18 Z" fill="#F2C86F"/>
                  <path d="M 9.5 15 Q 16 17 22.5 15 L 23 18 Q 16 20 9.5 15 Z" fill="#D96D42"/>
                  <path d="M 10 12 Q 16 14 22 12 L 22.5 15 Q 16 17 10 15 Z" fill="#2B9B7D"/>
                  <path d="M 10.5 9 Q 16 11 21.5 9 L 22 12 Q 16 14 10.5 12 Z" fill="#FFF5E4"/>
                  <path d="M 2 22 C 2 28, 30 28, 30 22 C 30 20, 25 18, 16 18 C 7 18, 2 20, 2 22 Z" fill="#F2C86F"/>
                  <path d="M 2 22 C 2 28, 30 28, 30 22" fill="none" stroke="#C38243" strokeWidth="1.5"/>
                </svg>
                <span className="relative z-0" style={sGradient}>S</span>
              </span>
              <span style={titleGradient}>bobinator</span>
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {processingCount > 0 && (
              <span className="premium-badge" style={{ color: 'var(--processing-text)', borderColor: 'var(--processing-ring)', background: 'var(--processing-bg)' }}>
                <span className="inline-flex h-2.5 w-2.5 rounded-full animate-pulse" style={{ background: 'var(--processing-text)' }} />
                {processingCount} sbobinatur{processingCount !== 1 ? 'e' : 'a'} in corso
              </span>
            )}
            <span className="premium-badge" style={{
              color: !apiReady ? (bridgeDelayed ? 'var(--error-text)' : 'var(--warning-text)') : !hasApiKey ? 'var(--text-secondary)' : !isApiKeyValid ? 'var(--warning-text)' : 'var(--success-text)',
              borderColor: !apiReady ? (bridgeDelayed ? 'var(--error-ring)' : 'var(--warning-ring)') : !hasApiKey ? 'var(--border-default)' : !isApiKeyValid ? 'var(--warning-ring)' : 'var(--success-ring)',
              background: !apiReady ? (bridgeDelayed ? 'var(--error-subtle)' : 'var(--warning-subtle)') : !hasApiKey ? 'rgba(255,255,255,0.02)' : !isApiKeyValid ? 'var(--warning-subtle)' : 'var(--success-subtle)',
            }}>
              <span className={`inline-flex h-2.5 w-2.5 rounded-full ${appState === 'processing' ? 'animate-pulse' : ''}`} style={{ background: !apiReady ? (bridgeDelayed ? 'var(--error-bg)' : 'var(--warning-bg)') : !hasApiKey ? 'var(--text-faint)' : !isApiKeyValid ? 'var(--warning-bg)' : 'var(--success-bg)' }} />
              {!apiReady ? (bridgeDelayed ? 'Bridge in ritardo' : 'Bridge in avvio') : !hasApiKey ? 'Configura API' : !isApiKeyValid ? 'Chiave non valida' : 'API pronta'}
            </span>
            <button
              onClick={() => setThemeMode(prev => prev === 'dark' ? 'light' : 'dark')}
              className="icon-button icon-btn-theme"
              aria-label={themeMode === 'dark' ? 'Attiva tema chiaro' : 'Attiva tema scuro'}
              title={themeMode === 'dark' ? 'Tema chiaro' : 'Tema scuro'}
            >
              {themeMode === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>
            <button
              onClick={() => {
                const next = !showConsole;
                setShowConsole(next);
                localStorage.setItem('show_console', String(next));
              }}
              className={`icon-button icon-btn-console${showConsole ? ' icon-button--active' : ''}`}
              title={showConsole ? 'Nascondi console' : 'Mostra console'}
              aria-label={showConsole ? 'Nascondi console' : 'Mostra console'}
            >
              <Terminal className="w-5 h-5" />
            </button>
            <button onClick={() => setIsSettingsOpen(true)} className="icon-button icon-btn-settings" aria-label="Apri impostazioni">
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>
        <AnimatePresence>
          {isPeakHour && !isPeakDismissed && (
            <motion.div
              key="peak-hour-banner"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              className="w-full overflow-hidden"
              style={{ borderTop: '1px solid var(--warning-ring, var(--border-default))', background: 'var(--warning-subtle)' }}
            >
              <div className="max-w-6xl mx-auto px-5 sm:px-6 py-2.5 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2.5 text-sm font-medium" style={{ color: 'var(--warning-text)' }}>
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>Fascia oraria di punta (15:00–20:00): tutti i modelli Gemini Flash possono subire <strong>rallentamenti o errori 503</strong> per traffico elevato sui server Google. Gemini 3 Flash è il più colpito; Gemini 2.5 Flash è generalmente più stabile, ma non immune da problemi.</span>
                </div>
                <button
                  onClick={() => { localStorage.setItem('peakBannerDismissedUntil', String(Date.now() + 3_600_000)); setIsPeakDismissed(true); }}
                  className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--warning-text)', padding: '2px', lineHeight: 1 }}
                  aria-label="Chiudi avviso fascia oraria"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </header>
      <AnimatePresence>
        {updateAvailable && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="w-full"
            style={{ background: 'var(--accent-subtle)', borderBottom: '1px solid var(--accent-ring, var(--border-default))' }}
          >
            <div className="max-w-6xl mx-auto px-5 sm:px-6 py-2.5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2.5 text-sm font-medium" style={{ color: 'var(--accent-text, var(--text-primary))' }}>
                <Zap className="w-4 h-4 shrink-0" />
                <span>Nuova versione disponibile: <strong>{updateAvailable}</strong></span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <a
                  href="#"
                  onClick={(e) => { e.preventDefault(); window.pywebview?.api?.open_url?.(GITHUB_RELEASES_URL); }}
                  className="premium-button-secondary compact-button text-xs px-3 py-1.5"
                  style={{ color: 'var(--accent-text, var(--text-primary))', borderColor: 'var(--accent-ring, var(--border-default))' }}
                >
                  Scarica
                </a>
                <button
                  onClick={() => dismissUpdate(updateAvailable)}
                  className="icon-button h-7 w-7 rounded-[10px]"
                  style={{ color: 'var(--text-muted)' }}
                  aria-label="Chiudi avviso aggiornamento"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <main className="max-w-3xl mx-auto px-5 sm:px-6 py-8 w-full flex-1 flex flex-col gap-6">

        {/* Processing Status Banner */}
        <AnimatePresence>
          {showProcessingBanner && (
            <ProcessingStatusBanner
              key="processing-banner"
              appState={appState}
              currentPhase={completionFlash ? '__completed__' : currentPhase}
              currentModel={currentModel}
              activeProgress={completionFlash ? 100 : activeProgress}
              workDone={workDone}
              workTotals={workTotals}
              currentFileIndex={batchCompleted}
              currentBatchTotal={batchTotal}
              currentFileName={bannerFile?.name}
              startedAt={bannerFile?.startedAt}
            />
          )}
        </AnimatePresence>

        {/* Onboarding / Drop Zone */}
        {uiMode === 'setup' ? (
          <div
            className="relative overflow-hidden rounded-2xl px-8 py-10 flex flex-col items-center gap-5"
            style={{ background: 'rgba(255,255,255,0.02)', border: '1.5px solid var(--border-default)' }}
          >
            <div className="flex flex-col items-center gap-2 text-center">
              <div className="w-14 h-14 rounded-full flex items-center justify-center shadow-xl" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-default)' }}>
                <Key className="w-7 h-7" style={{ color: 'var(--text-muted)' }} />
              </div>
              <h3 className="text-lg font-semibold mt-1" style={{ color: 'var(--text-primary)' }}>Configura la tua API Key</h3>
              <p className="text-sm leading-relaxed max-w-sm" style={{ color: 'var(--text-muted)' }}>
                El Sbobinator usa Google Gemini per trascrivere audio e video. Inserisci una chiave API gratuita per iniziare.
              </p>
            </div>

            {/* Inline key entry */}
            <div className="w-full max-w-md flex flex-col gap-2">
              <div className="relative">
                <input
                  type={setupKeyShowRaw ? 'text' : 'password'}
                  value={setupKeyInput}
                  onChange={e => setSetupKeyInput(e.target.value)}
                  onKeyDown={async e => {
                    if (e.key !== 'Enter') return;
                    if (!GEMINI_KEY_PATTERN.test(setupKeyInput.trim())) return;
                    if (setupKeySaving) return;
                    await handleSetupSave();
                  }}
                  placeholder="Incolla qui la tua API Key (AIzaSy...)"
                  className="app-input font-mono text-sm pr-10"
                  style={{
                    background: 'var(--bg-input)',
                    border: `1px solid ${
                      setupKeyInput.trim() && GEMINI_KEY_PATTERN.test(setupKeyInput.trim())
                        ? 'var(--success-ring)'
                        : setupKeyInput.trim()
                          ? 'var(--warning-ring)'
                          : 'var(--border-default)'
                    }`,
                    color: 'var(--text-primary)',
                  }}
                />
                <button
                  onClick={() => setSetupKeyShowRaw(v => !v)}
                  tabIndex={-1}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 opacity-50 hover:opacity-100 transition-opacity"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: '2px', lineHeight: 1 }}
                  aria-label={setupKeyShowRaw ? 'Nascondi chiave' : 'Mostra chiave'}
                >
                  {setupKeyShowRaw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {setupKeyInput.trim() && (
                <p className="text-xs" style={{ color: GEMINI_KEY_PATTERN.test(setupKeyInput.trim()) ? 'var(--success-text)' : 'var(--warning-text)' }}>
                  {GEMINI_KEY_PATTERN.test(setupKeyInput.trim()) ? '✓ Formato valido — premi Salva per continuare' : '⚠ Formato non valido — le chiavi iniziano con AIzaSy...'}
                </p>
              )}
              <button
                disabled={!GEMINI_KEY_PATTERN.test(setupKeyInput.trim()) || setupKeySaving}
                onClick={handleSetupSave}
                className="premium-button w-full"
                style={!GEMINI_KEY_PATTERN.test(setupKeyInput.trim()) ? { cursor: 'not-allowed', opacity: 0.5 } : {}}
              >
                <Key className="w-4 h-4" />
                {setupKeySaving ? 'Salvataggio…' : 'Salva e inizia'}
              </button>
              {setupKeyError && (
                <p className="text-xs" style={{ color: 'var(--error-text)' }}>❌ {setupKeyError}</p>
              )}
            </div>

            {/* 3-step mini guide */}
            <div className="w-full max-w-md rounded-xl px-5 py-4 flex flex-col gap-2.5" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-faint)' }}>Come ottenere la chiave in 1 minuto</p>
              <ol className="flex flex-col gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
                <li className="flex items-start gap-2">
                  <span className="shrink-0 w-4 h-4 rounded-full text-[10px] font-bold flex items-center justify-center" style={{ background: 'var(--accent-subtle)', color: 'var(--accent-text, var(--text-secondary))' }}>1</span>
                  <span>Vai su <a href="#" onClick={e => { e.preventDefault(); window.pywebview?.api?.open_url?.('https://aistudio.google.com/apikey'); }} className="underline hover:opacity-100 opacity-80" style={{ color: 'var(--accent-text, var(--text-secondary))' }}>aistudio.google.com/apikey</a></span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="shrink-0 w-4 h-4 rounded-full text-[10px] font-bold flex items-center justify-center" style={{ background: 'var(--accent-subtle)', color: 'var(--accent-text, var(--text-secondary))' }}>2</span>
                  <span>Clicca <strong>"Create API key"</strong> e copia la chiave</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="shrink-0 w-4 h-4 rounded-full text-[10px] font-bold flex items-center justify-center" style={{ background: 'var(--accent-subtle)', color: 'var(--accent-text, var(--text-secondary))' }}>3</span>
                  <span>Incollala nel campo qui sopra e premi <strong>Salva e inizia</strong></span>
                </li>
              </ol>
            </div>

            <button onClick={() => setIsSettingsOpen(true)} className="text-xs opacity-60 hover:opacity-100 transition-opacity flex items-center gap-1" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}>
              <Settings className="w-3.5 h-3.5" /> Apri impostazioni avanzate
            </button>
          </div>
        ) : uiMode !== 'processing' && uiMode !== 'canceling' ? (
          <div
            onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop} onClick={handleBrowseClick}
            className={`relative overflow-hidden rounded-2xl border-2 border-dashed transition-all duration-300 cursor-pointer flex flex-col items-center justify-center py-12 px-6 text-center group ${appState === 'processing' ? 'opacity-50 pointer-events-none' : ''}`}
            style={{
              borderColor: isDragging ? 'var(--accent-bg)' : 'var(--border-strong)',
              borderWidth: '2.5px',
              background: isDragging ? 'var(--accent-subtle)' : 'rgba(255,255,255,0.01)',
            }}
          >
            <input type="file" ref={fileInputRef} onChange={handleFileSelect} className="hidden" accept=".mp3,.m4a,.wav,.mp4,.mkv,.webm,.ogg,.flac,.aac" multiple />
            <div className="w-14 h-14 mb-4 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform duration-300 shadow-xl" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-default)' }}>
              <UploadCloud className="w-7 h-7" style={{ color: isDragging ? 'var(--accent-text)' : 'var(--text-muted)' }} />
            </div>
            <h3 className="text-lg font-medium mb-2" style={{ color: 'var(--text-primary)' }}>Clicca per sfogliare i file</h3>
            <p className="text-sm max-w-sm" style={{ color: 'var(--text-muted)' }}>
              Supporta audio e video (.mp3, .m4a, .wav, .mp4, .mkv, .webm, .ogg, .flac, .aac).<br/>Coda illimitata - elaborazione sequenziale.
            </p>
          </div>
        ) : null}

        {/* Batch Queue */}
        <AnimatePresence>
        {(pendingFiles.length > 0 || appState !== 'idle') && (
        <motion.div
          key="batch-queue"
          className="premium-panel p-5 sm:p-6 space-y-4"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0, transition: { duration: 0.2 } }}
          exit={{ opacity: 0, y: -8, transition: { duration: 0.15 } }}
        >
          <div className="flex flex-col gap-2 border-b pb-5" style={{ borderColor: 'var(--border-subtle)' }}>
            {/* Row 1: title + toggle */}
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-2xl font-semibold tracking-tight flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
                <FileAudio className="w-5 h-5" style={{ color: 'var(--text-muted)' }} />
                Coda di elaborazione
              </h2>
              <div
                className="flex items-center gap-2 shrink-0"
                title={autoContinue ? "Elabora i file in sequenza. Clicca per fermarsi dopo ogni file." : "L'app si fermerà dopo ogni file. Clicca per continuare in automatico."}
              >
                <ListOrdered className="w-4 h-4" style={{ color: autoContinue ? 'var(--accent-text)' : 'var(--text-muted)' }} />
                <button
                  type="button"
                  role="switch"
                  aria-checked={autoContinue}
                  onClick={() => setAutoContinue(v => !v)}
                  style={{
                    position: 'relative', display: 'inline-flex', alignItems: 'center',
                    width: '40px', height: '24px', borderRadius: '12px',
                    background: autoContinue ? 'var(--success-text)' : 'var(--border-default)',
                    border: 'none', cursor: 'pointer', transition: 'background 0.2s',
                    flexShrink: 0, padding: 0,
                  }}
                >
                  <span style={{
                    position: 'absolute', top: '4px', width: '16px', height: '16px',
                    borderRadius: '50%', background: 'white',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.3)', transition: 'transform 0.2s',
                    transform: autoContinue ? 'translateX(20px)' : 'translateX(4px)',
                  }} />
                </button>
              </div>
            </div>
            {/* Row 2: pills */}
            {pendingFiles.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="status-pill shrink-0 whitespace-nowrap">
                  {pendingFiles.length} {pendingFiles.length === 1 ? 'elemento' : 'elementi'}
                </span>
                {preferredModel && (
                  <span className="status-pill shrink-0 whitespace-nowrap">
                    Modello: {shortModelName(preferredModel)}
                  </span>
                )}
              </div>
            )}
          </div>

          <DndContext
            sensors={dndSensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
              <AnimatePresence>
                {pendingFiles.map((file) => {
                  const isActive = file.status === 'processing';
                  return (
                    <QueueFileCard
                      key={file.id}
                      file={file}
                      appState={appState}
                      currentPhase={isActive ? currentPhase : undefined}
                      onRemove={requestRemoveFile}
                      onRetry={(id) => dispatch({ type: 'queue/retry_one', id })}
                      onPreview={openPreview}
                      onOpenFile={openFile}
                    />
                  );
                })}
              </AnimatePresence>
            </SortableContext>
          </DndContext>
          {/* Action Panel */}
          {(appState !== 'idle' || queuedCount > 0) && (
            <div className="pt-4 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
              <AnimatePresence mode="wait">
                {appState === 'idle' && (
                  <motion.div key="idle" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                    <button onClick={() => startProcessing()} disabled={!canStart}
                      className="premium-button w-full text-lg"
                      style={canStart ? {} : { cursor: 'not-allowed' }}>
                      <Play className="w-5 h-5 fill-current" />
                      {!hasApiKey ? '⚠️ Inserisci API Key nelle impostazioni' : !isApiKeyValid ? '⚠️ API Key non valida' : `Avvia sbobinatura (${queuedCount} file)`}
                    </button>
                  </motion.div>
                )}
                {appState === 'processing' && (
                  <motion.div key="processing" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="flex justify-end">
                    <button onClick={() => setConfirmAction({ type: 'stop-processing' })} className="premium-button-secondary compact-button px-5 py-2" style={{ color: 'var(--error-text)', borderColor: 'var(--error-ring)', background: 'var(--bg-elevated)' }}>
                      <Square className="w-3.5 h-3.5 fill-current" /> Stop
                    </button>
                  </motion.div>
                )}
                {appState === 'canceling' && (
                  <motion.div key="canceling" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="flex justify-end">
                    <span className="text-sm flex items-center gap-1.5" style={{ color: 'var(--error-text)', opacity: 0.75, cursor: 'wait' }}>
                      <Square className="w-3 h-3 fill-current" />
                      Annullamento in corso
                    </span>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </motion.div>
        )}
        </AnimatePresence>

        {/* Sbobine completate */}
        <AnimatePresence>
          {doneFiles.length > 0 && (
            <motion.div
              key="completed-section"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8, transition: { duration: 0.15 } }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
              className="premium-panel p-5 sm:p-6 space-y-4"
            >
              <div className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-center sm:justify-between" style={{ borderColor: 'var(--border-subtle)' }}>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
                  <h2 className="text-2xl font-semibold tracking-tight flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
                    <CheckCircle className="w-5 h-5" style={{ color: 'var(--success-text)' }} />
                    Sbobine completate
                  </h2>
                  <span className="status-pill self-start sm:self-auto shrink-0 whitespace-nowrap" style={{ color: 'var(--success-text)', borderColor: 'var(--success-ring)', background: 'rgba(255,255,255,0.03)' }}>
                    {doneFiles.length} {doneFiles.length === 1 ? 'sbobina' : 'sbobine'}
                  </span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {doneFiles.length >= 5 && (
                    <div className="relative flex items-center">
                      <Search className="absolute left-2.5 w-3.5 h-3.5 pointer-events-none" style={{ color: 'var(--text-faint)' }} />
                      <input
                        type="text"
                        value={completedSearch}
                        onChange={e => setCompletedSearch(e.target.value)}
                        placeholder="Cerca..."
                        className="premium-button-secondary compact-button text-xs pl-7 pr-3 py-1.5 rounded-[13px] outline-none"
                        style={{ borderColor: 'var(--border-default)', background: 'rgba(255,255,255,0.03)', color: 'var(--text-primary)', width: '140px' }}
                      />
                    </div>
                  )}
                  {(appState === 'idle' || appState === 'processing') && (
                    <button
                      onClick={() => setConfirmAction({ type: 'clear-completed', count: doneFiles.length })}
                      className="premium-button-secondary compact-button text-xs"
                      style={{ color: 'var(--text-muted)', borderColor: 'var(--border-default)' }}
                    >
                      Pulisci tutto
                    </button>
                  )}
                </div>
              </div>

              <AnimatePresence>
                {filteredDoneFiles.map(file => (
                  <CompletedFileCard
                    key={file.id}
                    file={file}
                    isNewest={file.id === doneFiles[0]?.id}
                    onRemove={requestRemoveFile}
                    onPreview={openPreview}
                    onOpenFile={openFile}
                  />
                ))}
                {completedSearch.trim() && filteredDoneFiles.length === 0 && (
                  <motion.p
                    key="no-results"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="text-sm text-center py-6"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    Nessun risultato per "{completedSearch}"
                  </motion.p>
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Archivio storico */}
        <AnimatePresence>
          {archiveFiltered.length > 0 && (
            <motion.div
              ref={archivePanelRef}
              key="archive-section"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8, transition: { duration: 0.15 } }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
              className="premium-panel overflow-hidden"
            >
              <button
                onClick={() => {
                  const opening = !isArchiveOpen;
                  setIsArchiveOpen(opening);
                  if (opening) {
                    setTimeout(() => archivePanelRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 180);
                  } else {
                    setArchiveSearch('');
                    setArchivePage(0);
                  }
                }}
                className="w-full flex items-center justify-between gap-3 px-5 sm:px-6 py-4 transition-colors"
                style={{ background: 'none', border: 'none', cursor: 'pointer', borderBottom: isArchiveOpen ? '1px solid var(--border-subtle)' : 'none' }}
              >
                <div className="flex items-center gap-2">
                  <History className="w-5 h-5" style={{ color: 'var(--text-muted)' }} />
                  <span className="text-2xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Archivio Sbobine</span>
                  <span className="status-pill shrink-0 whitespace-nowrap">{archiveFiltered.length}</span>
                </div>
                {isArchiveOpen ? <ChevronUp className="w-4 h-4" style={{ color: 'var(--text-muted)' }} /> : <ChevronDown className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />}
              </button>
              <AnimatePresence>
                {isArchiveOpen && (
                  <motion.div
                    key="archive-list"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{
                      height: { duration: 0.25, ease: [0.4, 0, 0.2, 1] },
                      opacity: { duration: 0.2, delay: 0.04, ease: 'easeOut' },
                    }}
                    className="overflow-hidden"
                  >
                    {/* Toolbar: search + sort */}
                    <div className="px-5 sm:px-6 pt-4 pb-2 flex items-center gap-2">
                      <div className="relative flex-1 flex items-center">
                        <Search className="absolute left-2.5 w-3.5 h-3.5 pointer-events-none" style={{ color: 'var(--text-faint)' }} />
                        <input
                          type="text"
                          value={archiveSearch}
                          onChange={e => setArchiveSearch(e.target.value)}
                          placeholder="Cerca per nome..."
                          className="premium-button-secondary compact-button text-xs pr-3 py-1.5 rounded-[13px] outline-none w-full"
                          style={{ borderColor: 'var(--border-default)', background: 'rgba(255,255,255,0.03)', color: 'var(--text-primary)', paddingLeft: '2rem' }}
                        />
                      </div>
                      <button
                        onClick={() => setArchiveSort(s => s === 'newest' ? 'oldest' : 'newest')}
                        className="premium-button-secondary compact-button text-xs px-2.5 py-1.5 rounded-[13px] flex items-center gap-1 shrink-0"
                        style={{ color: 'var(--text-muted)', borderColor: 'var(--border-default)' }}
                        title={archiveSort === 'newest' ? 'Ordinate: più recenti prima' : 'Ordinate: più vecchie prima'}
                      >
                        {archiveSort === 'newest' ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
                        <span>{archiveSort === 'newest' ? 'Recente' : 'Vecchia'}</span>
                      </button>
                    </div>
                    <div className="px-5 sm:px-6 pb-4 flex flex-col gap-2">
                      <AnimatePresence mode="popLayout">
                      {archivePageData.map((session) => {
                        const ts = session.completed_at_iso ? new Date(session.completed_at_iso).getTime() : 0;
                        return (
                          <motion.div
                            key={session.session_dir}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -4, transition: { duration: 0.1 } }}
                            transition={{ duration: 0.18, ease: 'easeOut' }}
                            onClick={() => openPreview(session.html_path, session.name, session.input_path)}
                            className="flex items-center justify-between gap-3 rounded-xl px-4 py-3 cursor-pointer transition-colors"
                            style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
                          >
                            <div className="flex items-center gap-3 overflow-hidden flex-1">
                              <History className="w-4 h-4 shrink-0" style={{ color: 'var(--text-faint)' }} />
                              <div className="min-w-0 flex-1">
                                <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{session.name}</p>
                                <div className="flex flex-wrap items-center gap-2 mt-0.5 text-xs" style={{ color: 'var(--text-muted)' }}>
                                  {ts > 0 && <span>{formatRelativeTime(ts)}</span>}
                                  {session.effective_model && (
                                    <><span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} /><span>{shortModelName(session.effective_model)}</span></>
                                  )}
                                </div>
                                <div
                                  className="mt-0.5 flex items-center gap-1 text-[11px] hover:underline"
                                  style={{ color: 'var(--text-faint)', cursor: 'pointer' }}
                                  onClick={(e) => { e.stopPropagation(); openFile(session.html_path.replace(/[/\\][^/\\]+$/, '') || session.html_path); }}
                                  title={`Apri cartella: ${session.html_path.replace(/[/\\][^/\\]+$/, '') || session.html_path}`}
                                >
                                  <FolderOpen className="w-3 h-3 shrink-0" />
                                  <span className="truncate">
                                    {session.html_path.replace(/\\/g, '/').split('/').slice(-2).join('/')}
                                  </span>
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                              <button
                                onClick={e => { e.stopPropagation(); openFile(session.html_path); }}
                                className="icon-button compact-icon-button"
                                style={{ color: 'var(--text-muted)' }}
                                title="Apri nel browser"
                                aria-label="Apri nel browser"
                              >
                                <ExternalLink className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={e => { e.stopPropagation(); setConfirmAction({ type: 'delete-archive-session', sessionDir: session.session_dir, name: session.name }); }}
                                className="icon-button compact-icon-button"
                                style={{ color: 'var(--error-text)', borderColor: 'var(--error-ring)', background: 'var(--error-subtle)' }}
                                title="Elimina sessione"
                                aria-label="Elimina sessione"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </motion.div>
                        );
                      })}
                      {archiveSearch.trim() && archiveDisplayed.length === 0 && (
                        <motion.p
                          key="no-results"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          transition={{ duration: 0.15 }}
                          className="text-sm text-center py-4"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          Nessun risultato per &ldquo;{archiveSearch}&rdquo;
                        </motion.p>
                      )}
                      </AnimatePresence>
                      {archiveTotalPages > 1 && (
                        <div className="flex items-center justify-center gap-3 pt-2">
                          <button
                            onClick={() => setArchivePage(p => Math.max(0, p - 1))}
                            disabled={archivePage === 0}
                            className="icon-button compact-icon-button"
                            style={{ color: 'var(--text-muted)', opacity: archivePage === 0 ? 0.35 : 1 }}
                            aria-label="Pagina precedente"
                          >
                            <ChevronLeft className="w-4 h-4" />
                          </button>
                          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                            {archivePage + 1} / {archiveTotalPages}
                          </span>
                          <button
                            onClick={() => setArchivePage(p => Math.min(archiveTotalPages - 1, p + 1))}
                            disabled={archivePage >= archiveTotalPages - 1}
                            className="icon-button compact-icon-button"
                            style={{ color: 'var(--text-muted)', opacity: archivePage >= archiveTotalPages - 1 ? 0.35 : 1 }}
                            aria-label="Pagina successiva"
                          >
                            <ChevronRight className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Console */}
        {showConsole && <div className="console-shell console-shell-subtle">
          <div className="px-5 py-3 flex items-center justify-between" style={{ background: 'var(--console-header)', borderBottom: '1px solid var(--border-subtle)' }}>
            <h2 className="text-xs font-semibold uppercase tracking-wider flex items-center gap-2" style={{ color: 'var(--console-heading)' }}>
              <span className={`w-2 h-2 rounded-full ${appState === 'processing' ? 'animate-pulse' : ''}`} style={appState !== 'processing' ? { background: 'var(--console-heading)' } : { background: 'var(--processing-dot)' }} />
              Console
            </h2>
            <div className="flex items-center gap-1">
              {isConsoleExpanded && (
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(consoleLogs.join('\n'));
                    setIsCopied(true);
                    setTimeout(() => setIsCopied(false), 2000);
                  }}
                  className="p-1.5 rounded-md hover:bg-[var(--border-subtle)] transition-colors"
                  title={isCopied ? 'Copiato!' : 'Copia tutto'}
                  style={{ color: isCopied ? 'var(--success-text)' : 'var(--console-heading)', transition: 'color 0.2s' }}
                >
                  {isCopied ? <Check size={13} /> : <Copy size={13} />}
                </button>
              )}
              <button
                onClick={() => setIsConsoleExpanded(prev => !prev)}
                className="p-1.5 rounded-md hover:bg-[var(--border-subtle)] transition-colors"
                title={isConsoleExpanded ? 'Riduci' : 'Espandi'}
                style={{ color: 'var(--console-heading)' }}
              >
                <ChevronDown size={15} style={{ transform: isConsoleExpanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }} />
              </button>
            </div>
          </div>
          {isConsoleExpanded ? (
            <div
              ref={consoleScrollRef}
              className="console-scroll p-4 overflow-y-auto font-mono text-xs space-y-1 h-52 select-text"
              style={{ color: 'var(--console-text)', background: 'var(--console-bg)' }}
              onMouseEnter={() => { isMouseInConsoleRef.current = true; }}
              onMouseLeave={() => { isMouseInConsoleRef.current = false; }}
            >
              {consoleLogs.map((log, i) => {
                const color = log.includes('Errore') || log.includes('❌') || log.includes('[!]') || log.includes('Annullamento') ? 'var(--error-text)'
                  : log.includes('COMPLETATA') || log.includes('✅') ? 'var(--success-text)'
                  : log.includes('⚠') ? 'var(--warning-text)' : 'var(--console-text)';
                const match = log.match(/^\[\d{2}:\d{2}:\d{2}\]/);
                if (match) {
                  const ts = match[0];
                  const rest = log.slice(ts.length);
                  return <div key={i}><span style={{ color: 'var(--text-muted)' }}>{ts}</span><span style={{ color }}>{rest}</span></div>;
                }
                return <div key={i} style={{ color }}>{log}</div>;
              })}
            </div>
          ) : (
            <div className="px-5 pt-3 pb-4 text-[13px] leading-5" style={{ color: 'var(--console-text)', background: 'var(--console-bg)' }}>
              {lastConsoleMessage}
            </div>
          )}
        </div>}


      </main>

      {/* Footer Links */}
      <footer className="w-full shrink-0 mt-auto" style={{ borderTop: '1px solid var(--border-subtle)' }}>
        <div className="max-w-3xl mx-auto px-5 sm:px-6 py-4 flex items-center justify-center gap-3 text-sm" style={{ color: 'var(--text-muted)' }}>
        <a
          href="#"
          onClick={(e) => { e.preventDefault(); window.pywebview?.api?.open_url?.(GITHUB_URL); }}
          className="font-medium transition-colors hover:opacity-100 opacity-70 inline-flex items-center gap-2"
        >
          <Github className="w-4 h-4" />
          El Sbobinator - Progetto Open-Source
        </a>
        <span aria-hidden="true" className="opacity-40">•</span>
        <a
          href="#"
          onClick={(e) => { e.preventDefault(); window.pywebview?.api?.open_url?.(KOFI_URL); }}
          className="text-sm font-medium transition-colors hover:opacity-100 opacity-70"
        >
          Supporta il progetto su Ko-fi ☕
        </a>
        </div>
      </footer>

      {/* Modals */}
      <RegenerateModal
        prompt={regeneratePrompt}
        onAnswer={handleRegenerateAnswer}
        onDismiss={() => void handleRegenerateAnswer(null)}
      />
      <NewKeyModal isOpen={askNewKeyPrompt} onClose={() => setAskNewKeyPrompt(false)} />
      <DuplicateFileModal
        prompt={duplicatePrompt}
        onDismiss={() => setDuplicatePrompt(null)}
        onAddAgain={handleDuplicateAddAgain}
      />
      {confirmModalCopy && (
        <ConfirmActionModal
          isOpen={confirmAction !== null}
          title={confirmModalCopy.title}
          description={confirmModalCopy.description}
          confirmLabel={confirmModalCopy.confirmLabel}
          cancelLabel={confirmModalCopy.cancelLabel}
          onClose={() => setConfirmAction(null)}
          onConfirm={handleConfirmAction}
        />
      )}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        apiKey={apiKey}
        setApiKey={setApiKey}
        fallbackKeys={fallbackKeys}
        setFallbackKeys={setFallbackKeys}
        preferredModel={preferredModel}
        setPreferredModel={setPreferredModel}
        fallbackModels={fallbackModels}
        setFallbackModels={setFallbackModels}
        availableModels={availableModels}
        appendConsole={appendConsole}
      />
      <React.Suspense fallback={null}>
        <PreviewModal
          previewContent={preview.content}
          previewTitle={preview.title}
          htmlPath={preview.path}
          onClose={closePreview}
          audioSrc={preview.audioSrc}
          audioRelinkNeeded={preview.audioRelinkNeeded}
          onRelink={relinkPreviewAudio}
          previewInitAudio={preview.initAudio}
          previewInitScrollTop={preview.initScrollTop}
          onAudioStateChange={handleAudioStateChange}
          onScrollTopChange={handleScrollTopChange}
        />
      </React.Suspense>
    </div>
  );
}
