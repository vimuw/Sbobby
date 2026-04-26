import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { Github } from 'lucide-react';
import { GITHUB_URL, KOFI_URL } from './branding';
import { type ArchiveSession, type ElSbobinatorBridge, type PywebviewApi } from './bridge';
import { getDoneFiles, getPendingFiles, initialProcessingState, isSuccessfulProcessDone, processingReducer, type FileDescriptor, type FileItem, type ProcessDonePayload } from './appState';
import { GEMINI_KEY_PATTERN } from './utils';
import { useConsole } from './hooks/useConsole';
import { useTheme } from './hooks/useTheme';
import { useUpdateChecker } from './hooks/useUpdateChecker';
import { useQueuePersistence } from './hooks/useQueuePersistence';
import { useApiReady } from './hooks/useApiReady';
import { useBridgeCallbacks } from './hooks/useBridgeCallbacks';
import { useBodyScrollLock } from './hooks/useBodyScrollLock';
import { usePreview } from './hooks/usePreview';
import { ProcessingStatusBanner } from './components/ProcessingStatusBanner';
import { RegenerateModal } from './components/modals/RegenerateModal';
import { NewKeyModal } from './components/modals/NewKeyModal';
import { SettingsModal } from './components/modals/SettingsModal';
import { ConfirmActionModal } from './components/modals/ConfirmActionModal';
import { DuplicateFileModal, type AlreadyProcessedMatch, type DuplicatePrompt } from './components/modals/DuplicateFileModal';
import { buildArchiveLookup, filterArchiveSessionsByInputPath, getArchiveMatchesForFile } from './duplicateDetection';
import { AppHeader } from './components/AppHeader';
import { SetupPage } from './components/SetupPage';
import { DropZone } from './components/DropZone';
import { QueueSection } from './components/QueueSection';
import { CompletedSection } from './components/CompletedSection';
import { ArchiveSection } from './components/ArchiveSection';
import { ConsolePanel } from './components/ConsolePanel';
const PreviewModal = React.lazy(() => import('./components/modals/PreviewModal').then(m => ({ default: m.PreviewModal })));

declare global {
  interface Window {
    pywebview: { api?: PywebviewApi };
    elSbobinatorBridge: ElSbobinatorBridge;
  }
}

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

type UiMode = 'setup' | 'ready-empty' | 'ready-with-files' | 'processing' | 'canceling';
type ConfirmActionState =
  | { type: 'stop-processing' }
  | { type: 'remove-file'; fileId: string; fileName: string; isDone: boolean }
  | { type: 'clear-completed'; count: number }
  | { type: 'delete-archive-session'; sessionDir: string; name: string };

type PendingArchiveReplacement = {
  fileName: string;
  inputPath?: string;
  sessions: ArchiveSession[];
};

export default function App() {
  const [{ files, structuralVersion, appState, currentPhase, currentModel, activeProgress, workTotals, workDone }, dispatch] = useReducer(processingReducer, initialProcessingState);

  const { consoleLogs, appendConsole } = useConsole();
  const { themeMode, setThemeMode } = useTheme();
  const { updateAvailable, latestVersion, isCheckingUpdate, hasChecked, checkFailed, checkForUpdates, dismissUpdate } = useUpdateChecker();
  const {
    apiReady,
    bridgeDelayed,
    apiKey,
    setApiKey,
    hasProtectedKey,
    fallbackKeys,
    setFallbackKeys,
    preferredModel,
    setPreferredModel,
    fallbackModels,
    setFallbackModels,
    availableModels,
  } = useApiReady(appendConsole);

  const [archiveSessions, setArchiveSessions] = useState<ArchiveSession[]>([]);
  const { preview, openPreview, closePreview, relinkPreviewAudio, handleAudioStateChange, handleScrollTopChange } = usePreview({ appendConsole, dispatch, setArchiveSessions });

  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [regeneratePrompt, setRegeneratePrompt] = useState<{ filename: string; mode?: 'completed' | 'resume' } | null>(null);
  const [askNewKeyPrompt, setAskNewKeyPrompt] = useState(false);
  const [confirmAction, setConfirmAction] = useState<ConfirmActionState | null>(null);
  const [duplicatePrompt, setDuplicatePrompt] = useState<DuplicatePrompt>(null);

  const [isDragging, setIsDragging] = useState(false);
  const [showConsole, setShowConsole] = useState(() => localStorage.getItem('show_console') === 'true');
  const [autoContinue, setAutoContinue] = useState(() => localStorage.getItem('auto_continue') !== 'false');
  const [batchTotal, setBatchTotal] = useState(0);
  const [batchCompleted, setBatchCompleted] = useState(0);
  const [completionFlash, setCompletionFlash] = useState(false);

  const filesRef = useRef(files);
  const appStateRef = useRef(appState);
  const autoContinueRef = useRef(autoContinue);
  const duplicatePromptRef = useRef<DuplicatePrompt>(duplicatePrompt);
  const startProcessingRef = useRef<(isContinuation?: boolean) => Promise<boolean>>(() => Promise.resolve(false));
  const archiveSessionsRef = useRef<ArchiveSession[]>(archiveSessions);
  const pendingArchiveReplacementsRef = useRef<Map<string, PendingArchiveReplacement>>(new Map());
  const archiveReplacementCleanupInFlightRef = useRef<Set<string>>(new Set());

  filesRef.current = files;
  appStateRef.current = appState;
  autoContinueRef.current = autoContinue;
  duplicatePromptRef.current = duplicatePrompt;
  archiveSessionsRef.current = archiveSessions;

  useEffect(() => {
    try { localStorage.setItem('auto_continue', String(autoContinue)); } catch (_) {}
  }, [autoContinue]);

  const pendingFiles = useMemo(() => getPendingFiles(files), [files]);
  const doneFiles = useMemo(() => getDoneFiles(files), [files]);
  const { queuedCount } = useMemo(() => {
    let queuedCount = 0;
    for (const f of files) { if (f.status === 'queued') queuedCount++; }
    return { queuedCount };
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
  const showProcessingBanner = appState === 'processing' || appState === 'canceling' || completionFlash;
  const bannerFile = useMemo(
    () => files.find(f => f.status === 'processing') ?? (completionFlash ? doneFiles[0] : undefined),
    [files, completionFlash, doneFiles],
  );

  const refreshArchiveSessions = useCallback(async () => {
    try {
      const result = await window.pywebview?.api?.get_completed_sessions?.();
      if (result?.ok && result.sessions) setArchiveSessions(result.sessions);
    } catch (_) {}
  }, []);

  useEffect(() => {
    if (!apiReady) return;
    void refreshArchiveSessions();
  }, [apiReady, refreshArchiveSessions]);

  const finalizeArchiveReplacement = useCallback(async (fileId: string) => {
    const pendingReplacement = pendingArchiveReplacementsRef.current.get(fileId);
    if (!pendingReplacement || archiveReplacementCleanupInFlightRef.current.has(fileId)) return;
    archiveReplacementCleanupInFlightRef.current.add(fileId);
    const deletedSessionDirs: string[] = [];
    const currentFile = filesRef.current.find(file => file.id === fileId);
    const deletableSessions = filterArchiveSessionsByInputPath(
      pendingReplacement.inputPath || currentFile?.path,
      pendingReplacement.sessions,
    );
    const rawNewDir = currentFile?.outputDir
      || (currentFile?.outputHtml ? String(currentFile.outputHtml).replace(/[^/\\]+$/, '').replace(/[/\\]+$/, '') : undefined);
    const newOutputDirNorm = rawNewDir ? String(rawNewDir).replace(/[/\\]+$/, '').toLowerCase() : null;
    try {
      for (const session of deletableSessions) {
        const sessionDirNorm = String(session.session_dir).replace(/[/\\]+$/, '').toLowerCase();
        if (newOutputDirNorm && sessionDirNorm === newOutputDirNorm) continue;
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
        const deletedSet = new Set(deletedSessionDirs);
        setArchiveSessions(prev => prev.filter(s => !deletedSet.has(s.session_dir)));
      }
      if (deletedSessionDirs.length !== deletableSessions.length) {
        await refreshArchiveSessions();
      }
    } finally {
      pendingArchiveReplacementsRef.current.delete(fileId);
      archiveReplacementCleanupInFlightRef.current.delete(fileId);
    }
  }, [appendConsole, refreshArchiveSessions]);

  useEffect(() => {
    const currentFileIds = new Set(files.map(f => f.id));
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

  useEffect(() => {
    document.title = appState === 'processing' ? '⏳ El Sbobinator' : 'El Sbobinator';
  }, [appState]);

  useEffect(() => {
    if (appState !== 'processing' && confirmAction?.type === 'stop-processing') {
      setConfirmAction(null);
    }
  }, [appState, confirmAction]);

  const getFileFingerprint = useCallback((file: Pick<FileItem, 'path' | 'name' | 'size' | 'duration'>) => {
    const normalizedPath = String(file.path || '').trim().toLowerCase();
    if (normalizedPath) return `path:${normalizedPath}`;
    return `meta:${String(file.name || '').trim().toLowerCase()}::${Number(file.size || 0)}::${Math.round(Number(file.duration || 0))}`;
  }, []);

  const enqueueUniqueFiles = useCallback((incomingFiles: FileItem[]) => {
    if (incomingFiles.length === 0) return;
    if (duplicatePromptRef.current !== null) return;
    const currentFiles = filesRef.current;
    const currentArchive = archiveSessionsRef.current;
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
    if (alreadyProcessedMatches.length > 0) {
      setDuplicatePrompt({ kind: 'already-processed', matches: alreadyProcessedMatches, alsoInQueue: inQueueNames.length > 0 ? inQueueNames : undefined });
    } else if (inQueueNames.length > 0) {
      setDuplicatePrompt({ kind: 'in-queue', filenames: inQueueNames });
    }
  }, [dispatch, getFileFingerprint]);

  const handleDuplicateAddAgain = useCallback(async (matches: AlreadyProcessedMatch[]) => {
    setDuplicatePrompt(null);
    const sessionDirsToHide = new Set<string>();
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
          for (const s of archiveMatches) sessionDirsToHide.add(s.session_dir);
        }
        dispatch({ type: 'queue/remove', id: match.existingFile.id });
        dispatch({ type: 'queue/add', files: [{ ...match.incoming, id: replacementId, resumeSession: false }] });
      } else {
        pendingArchiveReplacementsRef.current.set(replacementId, {
          fileName: match.incoming.name,
          inputPath: match.incoming.path,
          sessions: match.sessions,
        });
        for (const s of match.sessions) sessionDirsToHide.add(s.session_dir);
        dispatch({ type: 'queue/add', files: [{ ...match.incoming, id: replacementId, resumeSession: false }] });
      }
    }
    if (sessionDirsToHide.size > 0) {
      setArchiveSessions(prev => prev.filter(s => !sessionDirsToHide.has(s.session_dir)));
    }
  }, [dispatch]);

  const requestRemoveFile = useCallback((id: string) => {
    const targetFile = filesRef.current.find(file => file.id === id);
    if (!targetFile) return;
    if (appState !== 'idle' && targetFile.status !== 'done') return;
    setConfirmAction({ type: 'remove-file', fileId: id, fileName: targetFile.name, isDone: targetFile.status === 'done' });
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
    return [{ id: file.id, path: nextPath, name: nextName, size: nextSize, duration: nextDuration, resume_session: file.resumeSession }] as FileDescriptor[];
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
      if (!fileDescriptors || fileDescriptors.length === 0) return false;
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
    void refreshArchiveSessions();
  }, [refreshArchiveSessions]);

  const handleConfirmAction = useCallback(() => {
    if (!confirmAction) return;
    if (confirmAction.type === 'stop-processing') { void confirmStopProcessing(); return; }
    if (confirmAction.type === 'remove-file') {
      const removedFile = filesRef.current.find(f => f.id === confirmAction.fileId);
      dispatch({ type: 'queue/remove', id: confirmAction.fileId });
      setConfirmAction(null);
      if (removedFile?.status === 'done') void refreshArchiveSessions();
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

  const handleRegenerateAnswer = async (ans: boolean | null) => {
    setRegeneratePrompt(null);
    try {
      if (window.pywebview?.api?.answer_regenerate) await window.pywebview.api.answer_regenerate(ans);
    } catch (e) { console.error('Failed to send answer to Python:', e); }
  };

  const openFile = useCallback(async (path: string) => {
    if (!window.pywebview?.api) return;
    const res = await window.pywebview.api.open_file(path);
    if (res && !res.ok) appendConsole(`❌ Impossibile aprire il file: ${res.error ?? path}`);
  }, [appendConsole]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (appState === 'idle') setIsDragging(true);
  }, [appState]);
  const handleDragLeave = useCallback(() => setIsDragging(false), []);
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (appStateRef.current !== 'idle') return;
    try {
      const w = window as WebViewHostWindow;
      if (w.chrome?.webview?.postMessageWithAdditionalObjects) {
        const names = Array.from(e.dataTransfer.files).map((f: File) => f.name);
        w.chrome.webview.postMessageWithAdditionalObjects('FilesDropped', e.dataTransfer.files);
        window.pywebview?.api?.collect_dropped_files?.(names);
      }
    } catch (_) {}
  }, []);

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

  const onFileContinued = useCallback(() => { setBatchCompleted(prev => prev + 1); }, []);
  const onBatchReset = useCallback(() => { setBatchTotal(0); setBatchCompleted(0); }, []);
  const onBatchFullyDone = useCallback((data: ProcessDonePayload) => {
    onBatchReset();
    if (isSuccessfulProcessDone(data)) {
      setCompletionFlash(true);
      setTimeout(() => setCompletionFlash(false), 5000);
    }
  }, [onBatchReset]);

  useQueuePersistence(files, structuralVersion, dispatch, appendConsole);
  useBridgeCallbacks({
    dispatch,
    appendConsole,
    filesRef,
    appStateRef,
    enqueueUniqueFiles,
    setRegeneratePrompt,
    setAskNewKeyPrompt,
    autoContinueRef,
    startProcessingRef,
    onFileContinued,
    onBatchReset,
    onBatchFullyDone,
    clearCompletionFlash: () => setCompletionFlash(false),
  });
  useBodyScrollLock(isSettingsOpen || regeneratePrompt !== null || preview.content !== null || askNewKeyPrompt || confirmAction !== null || duplicatePrompt !== null);

  const confirmModalCopy = useMemo(() => {
    if (!confirmAction) return null;
    if (confirmAction.type === 'stop-processing') {
      return { title: 'Interrompere la sbobinatura?', description: "Stai per fermare l'elaborazione in corso. Il processo verrà interrotto e il file attuale tornerà in coda. Vuoi continuare?", confirmLabel: 'Conferma stop', cancelLabel: 'Continua elaborazione' };
    }
    if (confirmAction.type === 'remove-file') {
      return { title: 'Rimuovere questo elemento?', description: confirmAction.isDone ? `"${confirmAction.fileName}" verrà spostata nell'archivio e rimossa dalla lista. Vuoi continuare?` : `"${confirmAction.fileName}" verrà rimossa dalla lista. Vuoi continuare?`, confirmLabel: 'Conferma rimozione', cancelLabel: 'Tieni elemento' };
    }
    if (confirmAction.type === 'delete-archive-session') {
      return { title: 'Eliminare questa sbobina?', description: `"${confirmAction.name}" e tutti i suoi dati di sessione verranno eliminati definitivamente dal disco. L'operazione è irreversibile.`, confirmLabel: 'Elimina definitivamente', cancelLabel: 'Annulla' };
    }
    return { title: 'Pulire le sbobine completate?', description: confirmAction.count === 1 ? "La sbobina completata verrà spostata nell'archivio e rimossa dalla lista. Vuoi continuare?" : `Le ${confirmAction.count} sbobine completate verranno spostate nell'archivio e rimosse dalla lista. Vuoi continuare?`, confirmLabel: 'Conferma pulizia', cancelLabel: 'Mantieni nella lista' };
  }, [confirmAction]);

  const archiveFiltered = useMemo(() => {
    const activeHtmlPaths = new Set(files.map(f => f.outputHtml).filter(Boolean));
    return archiveSessions.filter(s => !activeHtmlPaths.has(s.html_path));
  }, [archiveSessions, files]);

  return (
    <div className="app-shell min-h-screen font-sans flex flex-col" style={{ background: 'var(--bg-base)', color: 'var(--text-secondary)' }}>
      <AppHeader
        apiReady={apiReady}
        bridgeDelayed={bridgeDelayed}
        hasApiKey={hasApiKey}
        isApiKeyValid={isApiKeyValid}
        appState={appState}
        themeMode={themeMode}
        setThemeMode={setThemeMode}
        showConsole={showConsole}
        setShowConsole={setShowConsole}
        setIsSettingsOpen={setIsSettingsOpen}
        updateAvailable={updateAvailable}
        latestVersion={latestVersion}
        dismissUpdate={dismissUpdate}
      />
      <main className="flex-1 max-w-3xl w-full mx-auto px-5 sm:px-6 py-8 flex flex-col gap-6">
        {showProcessingBanner && (
          <ProcessingStatusBanner
            appState={appState}
            currentPhase={completionFlash ? '__completed__' : currentPhase}
            currentModel={currentModel}
            activeProgress={completionFlash ? 100 : activeProgress}
            workTotals={workTotals}
            workDone={workDone}
            currentFileIndex={batchCompleted}
            currentBatchTotal={batchTotal}
            currentFileName={bannerFile?.name}
            startedAt={bannerFile?.startedAt}
          />
        )}

        {uiMode === 'setup' ? (
          <SetupPage
            hasProtectedKey={hasProtectedKey}
            setIsSettingsOpen={setIsSettingsOpen}
            onSaved={(key) => setApiKey(key)}
            preferredModel={preferredModel}
            fallbackKeys={fallbackKeys}
            fallbackModels={fallbackModels}
          />
        ) : uiMode !== 'processing' && uiMode !== 'canceling' && !completionFlash ? (
          <DropZone
            isDragging={isDragging}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={handleBrowseClick}
          />
        ) : null}

        <QueueSection
          pendingFiles={pendingFiles}
          appState={appState}
          autoContinue={autoContinue}
          setAutoContinue={setAutoContinue}
          preferredModel={preferredModel}
          queuedCount={queuedCount}
          canStart={canStart}
          hasApiKey={hasApiKey}
          isApiKeyValid={isApiKeyValid}
          currentPhase={currentPhase}
          dndSensors={dndSensors}
          onDragEnd={handleDragEnd}
          onRemove={requestRemoveFile}
          onRetry={(id) => dispatch({ type: 'queue/retry_one', id })}
          onPreview={openPreview}
          onOpenFile={openFile}
          onStart={() => void startProcessing()}
          onStop={() => setConfirmAction({ type: 'stop-processing' })}
        />

        <CompletedSection
          doneFiles={doneFiles}
          appState={appState}
          onRemove={(id) => {
            const f = filesRef.current.find(f => f.id === id);
            if (!f) return;
            if (appState !== 'idle' && f.status !== 'done') return;
            setConfirmAction({ type: 'remove-file', fileId: id, fileName: f.name, isDone: true });
          }}
          onPreview={openPreview}
          onOpenFile={openFile}
          onClearAll={() => setConfirmAction({ type: 'clear-completed', count: doneFiles.length })}
        />

        <ArchiveSection
          sessions={archiveFiltered}
          onPreview={openPreview}
          onOpenFile={openFile}
          onDeleteSession={(sessionDir, name) => setConfirmAction({ type: 'delete-archive-session', sessionDir, name })}
        />

        {showConsole && (
          <ConsolePanel
            consoleLogs={consoleLogs}
            lastConsoleMessage={lastConsoleMessage}
            appState={appState}
          />
        )}
      </main>

      <footer className="text-center py-6 text-sm flex items-center justify-center gap-4" style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)' }}>
        <a href="#" onClick={e => { e.preventDefault(); window.pywebview?.api?.open_url?.(GITHUB_URL); }} className="flex items-center gap-1 hover:opacity-80 transition-opacity" style={{ color: 'inherit', textDecoration: 'none' }}>
          <Github className="w-3.5 h-3.5" /> Progetto Open-Source — GitHub
        </a>
        <span>·</span>
        <a href="#" onClick={e => { e.preventDefault(); window.pywebview?.api?.open_url?.(KOFI_URL); }} className="hover:opacity-80 transition-opacity" style={{ color: 'inherit', textDecoration: 'none' }}>
          ☕ Offrimi un caffè su Ko-fi!
        </a>
      </footer>

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
        hasProtectedKey={hasProtectedKey}
        fallbackKeys={fallbackKeys}
        setFallbackKeys={setFallbackKeys}
        preferredModel={preferredModel}
        setPreferredModel={setPreferredModel}
        fallbackModels={fallbackModels}
        setFallbackModels={setFallbackModels}
        availableModels={availableModels}
        appendConsole={appendConsole}
        latestVersion={latestVersion}
        checkForUpdates={checkForUpdates}
        isCheckingUpdate={isCheckingUpdate}
        hasChecked={hasChecked}
        checkFailed={checkFailed}
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
