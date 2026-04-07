import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { motion, AnimatePresence } from 'motion/react';
import {
  CheckCircle,
  FileAudio,
  FileText,
  Github,
  Moon,
  Play,
  Search,
  Settings,
  Square,
  Sun,
  UploadCloud,
  X,
  Zap,
} from 'lucide-react';
import { GITHUB_RELEASES_URL, GITHUB_URL, KOFI_URL } from './branding';
import { type BridgeCallbacks, type PywebviewApi } from './bridge';
import { getDoneFiles, getPendingFiles, initialProcessingState, processingReducer, type AppStatus, type FileDescriptor, type FileItem } from './appState';
import { GEMINI_KEY_PATTERN } from './utils';
import { useConsole } from './hooks/useConsole';
import { useTheme } from './hooks/useTheme';
import { useUpdateChecker } from './hooks/useUpdateChecker';
import { useQueuePersistence } from './hooks/useQueuePersistence';
import { useApiReady } from './hooks/useApiReady';
import { useBridgeCallbacks } from './hooks/useBridgeCallbacks';
import { useBodyScrollLock } from './hooks/useBodyScrollLock';
import { CompletedFileCard, QueueFileCard } from './components/QueueFileCard';
import { RegenerateModal } from './components/modals/RegenerateModal';
import { NewKeyModal } from './components/modals/NewKeyModal';
import { SettingsModal } from './components/modals/SettingsModal';
import { loadEditorSession, saveEditorSession, type EditorSession } from './editorSessions';
import { normalizePreviewHtmlContent } from './previewHtml';
const PreviewModal = React.lazy(() => import('./components/modals/PreviewModal').then(m => ({ default: m.PreviewModal })));

const EMPTY_WORK = { chunks: 0, macro: 0, boundary: 0 };

declare global {
  interface Window {
    pywebview: { api?: PywebviewApi };
    elSbobinatorBridge: BridgeCallbacks;
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

export default function App() {
  const [{ files, structuralVersion, appState, currentPhase, activeProgress, workTotals, workDone, stepMetrics }, dispatch] = useReducer(processingReducer, initialProcessingState);

  // --- Extracted hooks ---
  const { consoleLogs, appendConsole } = useConsole();
  const { themeMode, setThemeMode } = useTheme();
  const { updateAvailable, dismissUpdate } = useUpdateChecker();
  const { apiReady, apiKey, setApiKey, fallbackKeys, setFallbackKeys } = useApiReady(appendConsole);

  // --- Modal state ---
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [regeneratePrompt, setRegeneratePrompt] = useState<{ filename: string; mode?: 'completed' | 'resume' } | null>(null);
  const [askNewKeyPrompt, setAskNewKeyPrompt] = useState(false);

  // --- Preview state ---
  const [preview, setPreview] = useState<PreviewState>(initialPreviewState);

  // --- UI state ---
  const [isDragging, setIsDragging] = useState(false);
  const [isConsoleExpanded, setIsConsoleExpanded] = useState(false);
  const [showEmptyState, setShowEmptyState] = useState(() => files.length === 0);
  const [completedSearch, setCompletedSearch] = useState('');

  // --- Refs ---
  const fileInputRef = useRef<HTMLInputElement>(null);
  const filesRef = useRef<FileItem[]>([]);
  const appStateRef = useRef<AppStatus>('idle');
  const currentEditorSessionRef = useRef<EditorSession>({});
  const currentPreviewSessionKeyRef = useRef<string | null>(null);

  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  useEffect(() => {
    if (files.some(f => f.status !== 'done')) setShowEmptyState(false);
  }, [files]);

  useEffect(() => {
    appStateRef.current = appState;
  }, [appState]);

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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // --- Queue persistence ---
  useQueuePersistence(files, structuralVersion, dispatch, appendConsole);

  // --- File deduplication ---
  const getFileFingerprint = useCallback((file: Pick<FileItem, 'path' | 'name' | 'size' | 'duration'>) => {
    const normalizedPath = String(file.path || '').trim().toLowerCase();
    if (normalizedPath) return `path:${normalizedPath}`;
    return `meta:${String(file.name || '').trim().toLowerCase()}::${Number(file.size || 0)}::${Math.round(Number(file.duration || 0))}`;
  }, []);

  const enqueueUniqueFiles = useCallback((incomingFiles: FileItem[]) => {
    if (incomingFiles.length === 0) return;
    const seen = new Set(filesRef.current.map(file => getFileFingerprint(file)));
    const uniqueFiles: FileItem[] = [];
    let skippedDuplicates = 0;
    for (const file of incomingFiles) {
      const fingerprint = getFileFingerprint(file);
      if (seen.has(fingerprint)) { skippedDuplicates += 1; continue; }
      seen.add(fingerprint);
      uniqueFiles.push(file);
    }
    if (uniqueFiles.length > 0) dispatch({ type: 'queue/add', files: uniqueFiles });
    if (skippedDuplicates > 0) appendConsole(`${skippedDuplicates} file ${skippedDuplicates === 1 ? 'gia presente in coda ignorato.' : 'gia presenti in coda ignorati.'}`);
  }, [appendConsole, getFileFingerprint]);

  // --- Bridge callbacks ---
  useBridgeCallbacks({ dispatch, appendConsole, filesRef, appStateRef, enqueueUniqueFiles, setRegeneratePrompt, setAskNewKeyPrompt });

  // --- Body scroll lock ---
  const isModalOpen = isSettingsOpen || regeneratePrompt !== null || preview.content !== null || askNewKeyPrompt;
  useBodyScrollLock(isModalOpen);

  // --- Handlers ---
  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); if (appState === 'idle') setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (appStateRef.current !== 'idle' || !e.dataTransfer.files.length) return;
    const w = window as any;
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

  const removeFile = useCallback((id: string) => {
    if (appState !== 'idle') return;
    dispatch({ type: 'queue/remove', id });
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
    const resolvedFiles: FileDescriptor[] = [];
    const pathChecks = await Promise.all(
      queuedFiles.map(async file => {
        const p = String(file.path || '').trim();
        const exists = p && api?.check_path_exists ? Boolean((await api.check_path_exists(p))?.exists) : Boolean(p);
        return { file, exists };
      })
    );
    for (const { file, exists: sourceExists } of pathChecks) {
      let nextPath = String(file.path || '').trim();
      let nextName = file.name;
      let nextSize = file.size;
      let nextDuration = file.duration;
      if (!sourceExists) {
        if (!api?.ask_media_file) { appendConsole(`Impossibile ricollegare l'audio per ${file.name}.`); continue; }
        appendConsole(`Audio non trovato per ${file.name}. Selezionalo di nuovo per continuare.`);
        const selectedFile = await api.ask_media_file();
        if (!selectedFile?.path) { appendConsole(`Avvio annullato: audio non ricollegato per ${file.name}.`); continue; }
        nextPath = selectedFile.path; nextName = selectedFile.name; nextSize = selectedFile.size; nextDuration = selectedFile.duration || 0;
        dispatch({ type: 'queue/update_source', id: file.id, path: nextPath, name: nextName, size: nextSize, duration: nextDuration });
        appendConsole(`Audio ricollegato: ${nextName}`);
      }
      resolvedFiles.push({ id: file.id, path: nextPath, name: nextName, size: nextSize, duration: nextDuration });
    }
    return resolvedFiles;
  }, [appendConsole]);

  const startProcessing = async () => {
    if (queuedCount === 0 || !apiKey.trim()) return;
    if (window.pywebview?.api) {
      dispatch({ type: 'app/set_status', status: 'processing' });
      try {
        const fileDescriptors = await resolveQueuedFilesForProcessing();
        if (!fileDescriptors || fileDescriptors.length === 0) {
          dispatch({ type: 'app/set_status', status: 'idle' });
          return;
        }
        const result = await window.pywebview.api.start_processing?.(fileDescriptors, apiKey.trim(), true);
        if (!result?.ok) {
          dispatch({ type: 'app/set_status', status: 'idle' });
          appendConsole(`❌ ${result?.error || "Impossibile avviare l'elaborazione."}`);
        }
      } catch (e: any) {
        dispatch({ type: 'app/set_status', status: 'idle' });
        appendConsole(`❌ Errore avvio: ${e?.message || e}`);
      }
    }
  };

  const stopProcessing = async () => {
    dispatch({ type: 'app/set_status', status: 'canceling' });
    appendConsole('[!] Annullamento in corso, attendere prego...');
    if (window.pywebview?.api) await window.pywebview.api.stop_processing?.();
  };

  const handleRegenerateAnswer = async (ans: boolean) => {
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
    if (!window.pywebview?.api?.ask_media_file || !preview.fileId) return;
    try {
      const selectedFile = await window.pywebview.api.ask_media_file();
      if (!selectedFile?.path) return;
      dispatch({ type: 'queue/update_source', id: preview.fileId, path: selectedFile.path, name: selectedFile.name, size: selectedFile.size, duration: selectedFile.duration });
      setPreview(prev => ({ ...prev, sourcePath: selectedFile.path }));
      await loadPreviewAudio(selectedFile.path);
      appendConsole(`Audio ricollegato: ${selectedFile.name}`);
    } catch (error: any) { appendConsole(`❌ Impossibile ricollegare l'audio: ${error?.message || error}`); }
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
      } catch (e: any) { appendConsole(`❌ Errore JS anteprima: ${e.message || e}`); }
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

  const handleAudioStateChange = useCallback(({ currentTime, playbackRate, volume }: { currentTime: number; playbackRate: number; volume: number }) => {
    currentEditorSessionRef.current = { ...currentEditorSessionRef.current, audioTime: currentTime, playbackRate, volume };
  }, []);

  const handleScrollTopChange = useCallback((scrollTop: number) => {
    currentEditorSessionRef.current = { ...currentEditorSessionRef.current, scrollTop };
  }, []);

  const openFile = useCallback(async (path: string) => {
    if (window.pywebview?.api) await window.pywebview.api.open_file(path);
  }, []);


  // --- Computed values ---
  const { queuedCount, doneCount, errorCount, processingCount } = useMemo(() => {
    let queuedCount = 0, doneCount = 0, errorCount = 0, processingCount = 0;
    for (const f of files) {
      if (f.status === 'queued') queuedCount++;
      else if (f.status === 'done') doneCount++;
      else if (f.status === 'error') errorCount++;
      else if (f.status === 'processing') processingCount++;
    }
    return { queuedCount, doneCount, errorCount, processingCount };
  }, [files]);
  const hasApiKey = Boolean(apiKey.trim());
  const isApiKeyValid = GEMINI_KEY_PATTERN.test(apiKey.trim());
  const canStart = queuedCount > 0 && hasApiKey && isApiKeyValid;
  const shouldShowActionPanel = appState !== 'idle' || queuedCount > 0;
  const lastConsoleMessage = consoleLogs.length > 0 ? consoleLogs[consoleLogs.length - 1] : 'Pronto per iniziare.';

  const computeEta = (): string | null => {
    const active = stepMetrics.chunks ?? stepMetrics.macro ?? stepMetrics.boundary;
    if (!active || active.total <= 0 || active.avgSeconds <= 0) return null;
    const remaining = active.total - active.done;
    if (remaining <= 0) return null;
    const secs = Math.round(active.avgSeconds * remaining);
    if (secs < 60) return `~${secs}s`;
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return s > 0 ? `~${m}m ${s}s` : `~${m}m`;
  };
  const etaLabel = computeEta();

  useEffect(() => {
    if (appState === 'processing') {
      document.title = etaLabel ? `[ETA ${etaLabel}] El Sbobinator` : '⏳ El Sbobinator';
    } else {
      document.title = 'El Sbobinator';
    }
  }, [appState, etaLabel]);

  const titleGradient = { background: 'linear-gradient(90deg, var(--gradient-title-from), var(--gradient-title-to))', WebkitBackgroundClip: 'text' as const, WebkitTextFillColor: 'transparent' };
  const sGradient = { background: 'linear-gradient(90deg, var(--gradient-s-from), var(--gradient-s-to))', WebkitBackgroundClip: 'text' as const, WebkitTextFillColor: 'transparent' };

  const pendingFiles = useMemo(() => getPendingFiles(files), [files]);
  const doneFiles = useMemo(() => getDoneFiles(files), [files]);
  const filteredDoneFiles = useMemo(
    () => completedSearch.trim()
      ? doneFiles.filter(f => f.name.toLowerCase().includes(completedSearch.toLowerCase()))
      : doneFiles,
    [doneFiles, completedSearch],
  );

  const sortableIds = useMemo(() => pendingFiles.map(f => f.id), [pendingFiles]);

  return (
    <div className="app-shell min-h-screen font-sans flex flex-col" style={{ background: 'var(--bg-base)', color: 'var(--text-secondary)' }}>

      {/* Top Navigation */}
      <header className="sticky top-0 z-40 backdrop-blur-2xl" style={{ borderBottom: '1px solid var(--border-subtle)', background: 'rgba(16, 13, 11, 0.08)' }}>
        <div className="max-w-3xl mx-auto px-5 sm:px-6 min-h-[84px] flex items-center justify-between gap-4">
          <div className="flex items-center gap-1.5">
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
              color: !apiReady ? 'var(--warning-text)' : hasApiKey ? 'var(--success-text)' : 'var(--text-secondary)',
              borderColor: !apiReady ? 'var(--warning-ring)' : hasApiKey ? 'var(--success-ring)' : 'var(--border-default)',
              background: !apiReady ? 'var(--warning-subtle)' : hasApiKey ? 'var(--success-subtle)' : 'rgba(255,255,255,0.02)',
            }}>
              <span className={`inline-flex h-2.5 w-2.5 rounded-full ${appState === 'processing' ? 'animate-pulse' : ''}`} style={{ background: !apiReady ? 'var(--warning-bg)' : hasApiKey ? 'var(--success-bg)' : 'var(--text-faint)' }} />
              {!apiReady ? 'Bridge in avvio' : hasApiKey ? 'API pronta' : 'Configura API'}
            </span>
            <button
              onClick={() => setThemeMode(prev => prev === 'dark' ? 'light' : 'dark')}
              className="icon-button icon-btn-theme"
              aria-label={themeMode === 'dark' ? 'Attiva tema chiaro' : 'Attiva tema scuro'}
              title={themeMode === 'dark' ? 'Tema chiaro' : 'Tema scuro'}
            >
              {themeMode === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>
            <button onClick={() => setIsSettingsOpen(true)} className="icon-button icon-btn-settings" aria-label="Apri impostazioni">
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>
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

        {/* Drop Zone */}
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

        {/* Batch Queue */}
        <div className="premium-panel p-5 sm:p-6 space-y-4">
          <div className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-center sm:justify-between" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
              <h2 className="text-2xl font-semibold tracking-tight flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
                <FileAudio className="w-5 h-5" style={{ color: 'var(--text-muted)' }} />
                Coda di elaborazione
              </h2>
              {pendingFiles.length > 0 && (
                <span className="status-pill self-start sm:self-auto shrink-0 whitespace-nowrap">
                  {pendingFiles.length} {pendingFiles.length === 1 ? 'elemento' : 'elementi'}
                </span>
              )}
            </div>
            {errorCount > 0 && appState === 'idle' && (
              <button onClick={() => dispatch({ type: 'queue/retry_failed' })} className="premium-button-secondary compact-button" style={{ color: 'var(--warning-text)', borderColor: 'var(--warning-ring)', background: 'var(--warning-subtle)' }}>
                Riprova falliti ({errorCount})
              </button>
            )}
          </div>

          <DndContext
            sensors={dndSensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
              <AnimatePresence mode="popLayout" onExitComplete={() => { if (!filesRef.current.some(f => f.status !== 'done')) setShowEmptyState(true); }}>
                {pendingFiles.map((file) => {
                  const isActive = file.status === 'processing';
                  return (
                    <QueueFileCard
                      key={file.id}
                      file={file}
                      appState={appState}
                      currentPhase={isActive ? currentPhase : undefined}
                      workDone={isActive ? workDone : EMPTY_WORK}
                      workTotals={isActive ? workTotals : EMPTY_WORK}
                      etaLabel={isActive ? etaLabel : null}
                      activeProgress={isActive ? activeProgress : undefined}
                      onRemove={removeFile}
                      onPreview={openPreview}
                      onOpenFile={openFile}
                      onOpenDir={openFile}
                    />
                  );
                })}
              </AnimatePresence>
            </SortableContext>
          </DndContext>
          <AnimatePresence>
            {showEmptyState && (
              <motion.div
                key="empty-state"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: 0.15 } }}
                exit={{ opacity: 0, transition: { duration: 0 } }}
                className="p-10 rounded-[26px] text-center flex flex-col items-center border border-dashed"
                style={{ borderColor: 'var(--border-default)', background: 'rgba(255,255,255,0.03)' }}>
                <div className="w-14 h-14 rounded-[20px] flex items-center justify-center mb-4" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-default)' }}>
                  <FileText className="w-5 h-5" style={{ color: 'var(--text-faint)' }} />
                </div>
                <p className="text-sm leading-6 max-w-md" style={{ color: 'var(--text-muted)' }}>Nessun file in coda. Aggiungi un file per iniziare.</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

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
                  {appState !== 'processing' && (
                    <button
                      onClick={() => { dispatch({ type: 'queue/clear_completed' }); setCompletedSearch(''); }}
                      className="premium-button-secondary compact-button text-xs"
                      style={{ color: 'var(--text-muted)', borderColor: 'var(--border-default)' }}
                    >
                      Pulisci tutto
                    </button>
                  )}
                </div>
              </div>

              <AnimatePresence mode="popLayout">
                {filteredDoneFiles.map(file => (
                  <CompletedFileCard
                    key={file.id}
                    file={file}
                    appState={appState}
                    onRemove={removeFile}
                    onPreview={openPreview}
                    onOpenFile={openFile}
                    onOpenDir={openFile}
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

        {/* Console */}
        <div className="console-shell console-shell-subtle">
          <div className="px-5 py-3 flex items-center justify-between" style={{ background: 'var(--console-header)', borderBottom: '1px solid var(--border-subtle)' }}>
            <h2 className="text-xs font-semibold uppercase tracking-wider flex items-center gap-2" style={{ color: 'var(--text-muted)' }}>
              <span className={`w-2.5 h-2.5 rounded-full ${appState === 'processing' ? 'animate-pulse' : ''}`} style={appState !== 'processing' ? { background: 'var(--text-faint)' } : { background: 'var(--processing-dot)' }} />
              Console
            </h2>
            <div className="flex items-center gap-2">
              <button onClick={() => setIsConsoleExpanded(prev => !prev)} className="premium-button-secondary compact-button px-2.5 py-1.5 text-[11px] rounded-[13px]" style={{ borderColor: 'var(--border-default)' }}>
                {isConsoleExpanded ? 'Riduci' : 'Espandi'}
              </button>
            </div>
          </div>
          {isConsoleExpanded ? (
            <div className="console-scroll p-4 overflow-y-auto font-mono text-xs space-y-1 h-52 select-text" style={{ color: 'var(--console-text)', background: 'var(--console-bg)' }}>
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
        </div>

        {/* Action Buttons */}
        {shouldShowActionPanel && (
          <div className="premium-panel p-4 sm:p-5 mt-1">
            <AnimatePresence mode="wait">
              {appState === 'idle' && (
                <motion.div key="idle" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                  <button onClick={startProcessing} disabled={!canStart}
                    className="premium-button w-full text-lg"
                    style={canStart ? {} : { cursor: 'not-allowed' }}>
                    <Play className="w-5 h-5 fill-current" />
                    {!hasApiKey ? '⚠️ Inserisci API Key nelle impostazioni' : !isApiKeyValid ? '⚠️ API Key non valida' : `Avvia sbobinatura (${queuedCount} file)`}
                  </button>
                </motion.div>
              )}
              {appState === 'processing' && (
                <motion.div key="processing" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="w-full flex gap-4">
                  <div className="flex-1 py-4 rounded-[20px] flex items-center justify-center gap-3" style={{ background: 'var(--processing-bg)', border: '1px solid var(--processing-ring)' }}>
                    <div className="relative flex h-3 w-3">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: 'var(--processing-text)' }} />
                      <span className="relative inline-flex rounded-full h-3 w-3" style={{ background: 'var(--processing-dot)' }} />
                    </div>
                    <span className="font-medium" style={{ color: 'var(--processing-text)' }}>Elaborazione in corso...</span>
                  </div>
                  <button onClick={stopProcessing} className="premium-button-secondary px-8 py-4" style={{ color: 'var(--error-text)', borderColor: 'var(--error-ring)', background: 'var(--bg-elevated)' }}>
                    <Square className="w-4 h-4 fill-current" /> Stop
                  </button>
                </motion.div>
              )}
              {appState === 'canceling' && (
                <motion.div key="canceling" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                  <button disabled className="premium-button w-full text-lg" style={{ background: 'var(--warning-subtle)', color: 'var(--warning-text)', borderColor: 'var(--warning-ring)', boxShadow: 'none', cursor: 'wait' }}>
                    <Square className="w-5 h-5 fill-current" />
                    Annullamento in corso...
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

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
      <RegenerateModal prompt={regeneratePrompt} onAnswer={handleRegenerateAnswer} />
      <NewKeyModal isOpen={askNewKeyPrompt} onClose={() => setAskNewKeyPrompt(false)} />
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        apiKey={apiKey}
        setApiKey={setApiKey}
        fallbackKeys={fallbackKeys}
        setFallbackKeys={setFallbackKeys}
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
