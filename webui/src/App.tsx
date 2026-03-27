import React, { Suspense, useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  AlertCircle,
  Check,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  FileAudio,
  FileText,
  FolderOpen,
  Github,
  Key,
  Moon,
  Play,
  Printer,
  Settings,
  Square,
  Sun,
  Trash2,
  UploadCloud,
  X,
  Zap,
} from 'lucide-react';
import { APP_NAME, APP_SHORT, APP_VERSION, GITHUB_API_RELEASES_URL, GITHUB_RELEASES_URL, GITHUB_URL, KOFI_URL } from './branding';
import { createBridge, type BridgeCallbacks, type PywebviewApi, type ValidationResult } from './bridge';
import { initialProcessingState, processingReducer, type AppStatus, type FileDescriptor, type FileItem } from './appState';

const LazyAudioPlayer = React.lazy(() => import('./AudioPlayer').then(module => ({ default: module.AudioPlayer })));
const LazyRichTextEditor = React.lazy(() => import('./RichTextEditor').then(module => ({ default: module.RichTextEditor })));
const QUEUE_STORAGE_KEY = 'el-sbobinator.queue.v1';
const THEME_STORAGE_KEY = 'el-sbobinator.theme.v1';
const EDITOR_SESSION_STORAGE_KEY = 'el-sbobinator.editor-sessions.v1';
const UPDATE_DISMISSED_KEY = 'el-sbobinator.dismissed-update.v1';
const UPDATE_LAST_CHECK_KEY = 'el-sbobinator.last-update-check.v1';
const UPDATE_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

type EditorSession = {
  audioTime?: number;
  playbackRate?: number;
  volume?: number;
  scrollTop?: number;
};

const loadEditorSession = (key: string): EditorSession => {
  try {
    const raw = window.localStorage.getItem(EDITOR_SESSION_STORAGE_KEY);
    if (!raw) return {};
    const sessions = JSON.parse(raw) as Record<string, EditorSession>;
    return sessions[key] ?? {};
  } catch (_) { return {}; }
};

const saveEditorSession = (key: string, session: EditorSession) => {
  try {
    const raw = window.localStorage.getItem(EDITOR_SESSION_STORAGE_KEY) ?? '{}';
    const sessions = JSON.parse(raw) as Record<string, EditorSession>;
    sessions[key] = session;
    window.localStorage.setItem(EDITOR_SESSION_STORAGE_KEY, JSON.stringify(sessions));
  } catch (_) {}
};

const SUPPORTED_FORMATS = ['MP3', 'M4A', 'WAV', 'MP4', 'MKV', 'WEBM', 'OGG', 'FLAC', 'AAC'];
const GEMINI_KEY_PATTERN = /^AIza[0-9A-Za-z_-]{20,}$/;
const EDITOR_IMAGE_ALLOWED_DATA_ATTRS = new Set(['data-editor-image', 'data-layout', 'data-align', 'data-width']);

const normalizePreviewHtmlContent = (content: string) => {
  const parsed = new DOMParser().parseFromString(`<body>${content || ''}</body>`, 'text/html');

  parsed.body.querySelectorAll('*').forEach(element => {
    const tag = element.tagName.toLowerCase();
    const isEditorImageContainer = tag === 'div' && element.hasAttribute('data-editor-image');
    const isEditorImageAsset = tag === 'img' && element.parentElement?.hasAttribute('data-editor-image');

    element.removeAttribute('align');

    if (!isEditorImageContainer && !isEditorImageAsset) {
      element.removeAttribute('style');
      element.removeAttribute('class');
      Array.from(element.attributes)
        .filter(attribute => attribute.name.startsWith('data-'))
        .forEach(attribute => element.removeAttribute(attribute.name));
      return;
    }

    if (isEditorImageContainer) {
      Array.from(element.attributes)
        .filter(attribute => attribute.name.startsWith('data-') && !EDITOR_IMAGE_ALLOWED_DATA_ATTRS.has(attribute.name))
        .forEach(attribute => element.removeAttribute(attribute.name));
      element.removeAttribute('class');
      return;
    }

    element.removeAttribute('class');
    Array.from(element.attributes)
      .filter(attribute => attribute.name.startsWith('data-'))
      .forEach(attribute => element.removeAttribute(attribute.name));
  });

  return parsed.body.innerHTML;
};

declare global {
  interface Window {
    pywebview: { api?: PywebviewApi };
    elSbobinatorBridge: BridgeCallbacks;
  }
}

export default function App() {
  const [{ files, appState, currentPhase }, dispatch] = useReducer(processingReducer, initialProcessingState);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [fallbackKeys, setFallbackKeys] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [apiReady, setApiReady] = useState(false);
  const [regeneratePrompt, setRegeneratePrompt] = useState<{filename: string; mode?: 'completed' | 'resume'} | null>(null);
  const [askNewKeyPrompt, setAskNewKeyPrompt] = useState(false);
  const [newKeyInput, setNewKeyInput] = useState('');
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [editedContent, setEditedContent] = useState<string>('');
  const [previewTitle, setPreviewTitle] = useState<string>('');
  const [previewPath, setPreviewPath] = useState<string>('');
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  const [previewFileId, setPreviewFileId] = useState<string | null>(null);
  const [previewSourcePath, setPreviewSourcePath] = useState<string>('');
  const [audioRelinkNeeded, setAudioRelinkNeeded] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const [isExportMenuOpen, setIsExportMenuOpen] = useState(false);
  const [autosaveStatus, setAutosaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [isValidatingEnvironment, setIsValidatingEnvironment] = useState(false);
  const [isConsoleExpanded, setIsConsoleExpanded] = useState(false);
  const [consoleLogs, setConsoleLogs] = useState<string[]>([
    `[${new Date().toLocaleTimeString()}] ${APP_NAME} avviato.`,
  ]);
  const [showApiKeys, setShowApiKeys] = useState(false);
  const [themeMode, setThemeMode] = useState<'light' | 'dark'>('dark');
  const [updateAvailable, setUpdateAvailable] = useState<string | null>(null);
  
  const [previewInitAudio, setPreviewInitAudio] = useState<{ time?: number; playbackRate?: number; volume?: number }>({});
  const [previewInitScrollTop, setPreviewInitScrollTop] = useState<number | undefined>(undefined);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const consoleEndRef = useRef<HTMLDivElement>(null);
  const filesRef = useRef<FileItem[]>([]);
  const appStateRef = useRef<AppStatus>('idle');
  const hasRestoredQueueRef = useRef(false);
  const lastPersistedPreviewRef = useRef('');
  const currentEditorSessionRef = useRef<EditorSession>({});
  const currentPreviewSessionKeyRef = useRef<string | null>(null);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  const appendConsole = useCallback((msg: string) => {
    setConsoleLogs(prev => {
      const next = [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`];
      return next.length > 300 ? next.slice(-300) : next;
    });
  }, []);

  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  useEffect(() => {
    appStateRef.current = appState;
  }, [appState]);

  useEffect(() => {
    try {
      const persistedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
      if (persistedTheme === 'light' || persistedTheme === 'dark') {
        setThemeMode(persistedTheme);
        return;
      }
    } catch (_) {}

    try {
      setThemeMode(window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    } catch (_) {
      setThemeMode('dark');
    }
  }, []);

  useEffect(() => {
    try {
      document.documentElement.dataset.theme = themeMode;
      document.documentElement.style.colorScheme = themeMode;
    } catch (_) {}

    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, themeMode);
    } catch (_) {}
  }, [themeMode]);

  useEffect(() => {
    const compareVersions = (a: string, b: string): number => {
      const parse = (v: string) => v.replace(/^v/, '').split('.').map(Number);
      const [aMaj, aMin, aPatch] = parse(a);
      const [bMaj, bMin, bPatch] = parse(b);
      return aMaj !== bMaj ? aMaj - bMaj : aMin !== bMin ? aMin - bMin : aPatch - bPatch;
    };

    try {
      const lastCheck = Number(window.localStorage.getItem(UPDATE_LAST_CHECK_KEY) || 0);
      if (Date.now() - lastCheck < UPDATE_CHECK_INTERVAL_MS) return;
      window.localStorage.setItem(UPDATE_LAST_CHECK_KEY, String(Date.now()));
    } catch (_) {}

    fetch(GITHUB_API_RELEASES_URL)
      .then(r => r.json())
      .then(data => {
        const latest: string = data?.tag_name;
        if (!latest) return;
        try {
          const dismissed = window.localStorage.getItem(UPDATE_DISMISSED_KEY);
          if (dismissed === latest) return;
        } catch (_) {}
        if (compareVersions(latest, APP_VERSION) > 0) {
          setUpdateAvailable(latest);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (hasRestoredQueueRef.current) return;
    hasRestoredQueueRef.current = true;
    try {
      const raw = window.localStorage.getItem(QUEUE_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed) || parsed.length === 0) return;

      const restoredFiles: FileItem[] = parsed.map((file: Partial<FileItem>, index: number) => ({
        id: String(file.id || `restored-${index}`),
        name: String(file.name || `file-${index}`),
        size: Number(file.size || 0),
        duration: Number(file.duration || 0),
        path: file.path ? String(file.path) : undefined,
        status: file.status === 'done' ? 'done' : 'queued',
        progress: file.status === 'done' ? 100 : 0,
        phase: file.status === 'done' ? 3 : 0,
        outputHtml: file.outputHtml ? String(file.outputHtml) : undefined,
        outputDir: file.outputDir ? String(file.outputDir) : undefined,
      }));

      dispatch({ type: 'queue/add', files: restoredFiles });
      appendConsole(`Coda ripristinata: ${restoredFiles.length} file.`);
    } catch (error) {
      console.error('Queue restore failed:', error);
    }
  }, [appendConsole]);

  useEffect(() => {
    try {
      if (files.length === 0) {
        window.localStorage.removeItem(QUEUE_STORAGE_KEY);
        return;
      }
      const persisted = files.map(file => ({
        id: file.id,
        name: file.name,
        size: file.size,
        duration: file.duration,
        path: file.path,
        status: file.status,
        outputHtml: file.outputHtml,
        outputDir: file.outputDir,
      }));
      window.localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(persisted));
    } catch (error) {
      console.error('Queue persist failed:', error);
    }
  }, [files]);

  // --- Wait for pywebview to inject the API, then load settings ---
  useEffect(() => {
    const onReady = async () => {
      if (apiReady) return;
      setApiReady(true);
      appendConsole('Connesso a Python.');
      try {
        const cfg = await window.pywebview.api?.load_settings?.();
        if (cfg?.api_key) setApiKey(cfg.api_key);
        if (cfg?.fallback_keys?.length) setFallbackKeys(cfg.fallback_keys.join('\n'));
      } catch (e) { console.error('Load settings failed:', e); }
    };

    window.addEventListener('pywebviewready', onReady);
    if (window.pywebview?.api) onReady();

    // Pre-warm bridge to avoid freeze-on-first-click
    const warmup = setTimeout(async () => {
      try { if (window.pywebview?.api) await window.pywebview.api.load_settings(); } catch (_) {}
    }, 100);

    const fallback = setTimeout(() => setApiReady(true), 5000);

    return () => {
      window.removeEventListener('pywebviewready', onReady);
      clearTimeout(warmup);
      clearTimeout(fallback);
    };
  }, [apiReady, appendConsole]);

  // --- Bridge: Python â†’ React callbacks ---
  useEffect(() => {
    window.elSbobinatorBridge = createBridge({
      dispatch,
      appendConsole,
      onRegenerate: data => setRegeneratePrompt(data),
      onFilesDropped: (droppedFiles) => {
        if (appStateRef.current !== 'idle') return;
        const filesToAdd = droppedFiles.map(f => ({
          id: Math.random().toString(36).substring(2, 9),
          name: f.name,
          size: f.size,
          duration: f.duration || 0,
          path: f.path,
          status: 'queued' as const,
          progress: 0,
          phase: 0,
        }));
        enqueueUniqueFiles(filesToAdd);
      },
      onAskNewKey: () => {
        setNewKeyInput('');
        setAskNewKeyPrompt(true);
      },
      onBatchDone: data => {
        if (!data?.cancelled && data?.total && data.completed === data.total && window.pywebview?.api?.show_notification && !document.hasFocus()) {
          window.pywebview.api.show_notification('Elaborazione completata', 'Tutti i file in coda sono stati sbobinati con successo.');
        }
      },
      onFileDone: data => {
        const currentFile = filesRef.current.find(file => file.id === data.id);
        if (currentFile && window.pywebview?.api?.show_notification && !document.hasFocus()) {
          window.pywebview.api.show_notification('File Completato!', `✅ ${currentFile.name} pronto.`);
        }
      },
    });
  }, [appendConsole]);

  useEffect(() => {
    const isModalOpen = isSettingsOpen || regeneratePrompt !== null || previewContent !== null || askNewKeyPrompt;
    if (isModalOpen) {
      const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
      document.body.style.overflow = 'hidden';
      document.body.style.paddingRight = `${scrollbarWidth}px`;
    } else {
      document.body.style.overflow = 'unset';
      document.body.style.paddingRight = '0px';
    }
    return () => { 
      document.body.style.overflow = 'unset'; 
      document.body.style.paddingRight = '0px';
    };
  }, [isSettingsOpen, regeneratePrompt, previewContent, askNewKeyPrompt]);

  useEffect(() => {
    consoleEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [consoleLogs]);



  // --- Handlers ---
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault(); 
    if (appState === 'idle') setIsDragging(true); 
  };
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
    // Aggiunto controllo più robusto per l'API Python
    if (!apiReady || !window.pywebview || !window.pywebview.api) {
      appendConsole('⚠ In attesa della connessione con Python... riprova tra un momento.');
      return;
    }

    try {
      const selectedFiles = await window.pywebview.api.ask_files?.();
      if (selectedFiles?.length > 0) {
        const filesToAdd: FileItem[] = selectedFiles.map((f: FileDescriptor) => ({
          id: Math.random().toString(36).substring(2, 9),
          name: f.name, size: f.size, duration: f.duration || 0,
          path: f.path, status: 'queued' as const, progress: 0, phase: 0,
        }));
        enqueueUniqueFiles(filesToAdd);
      }
    } catch (e) {
      appendConsole(`❌ Errore selezione file: ${e}`);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      const filesToAdd: FileItem[] = Array.from(e.target.files).map((file: File) => ({
        id: Math.random().toString(36).substring(2, 9),
        name: file.name, size: file.size, duration: 0,
        status: 'queued' as const, progress: 0, phase: 0,
      }));
      enqueueUniqueFiles(filesToAdd);
      e.target.value = '';
    }
  };

  const removeFile = (id: string) => {
    if (appState !== 'idle') return;
    dispatch({ type: 'queue/remove', id });
  };

  const moveFile = useCallback((id: string, direction: 'up' | 'down') => {
    if (appState !== 'idle') return;
    dispatch({ type: 'queue/move', id, direction });
  }, [appState]);

  const clearCompletedFiles = () => {
    if (appState !== 'idle') return;
    dispatch({ type: 'queue/clear_completed' });
  };

  const clearAllFiles = () => {
    if (appState !== 'idle') return;
    dispatch({ type: 'queue/clear_all' });
  };

  const formatSize = (bytes: number) => {
    if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / 1024).toFixed(0)} KB`;
  };

  const formatDuration = (seconds: number, fallback = '') => {
    if (!seconds) return fallback;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s.toString().padStart(2, '0')}s`;
    return `${s}s`;
  };

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
      if (seen.has(fingerprint)) {
        skippedDuplicates += 1;
        continue;
      }
      seen.add(fingerprint);
      uniqueFiles.push(file);
    }

    if (uniqueFiles.length > 0) {
      dispatch({ type: 'queue/add', files: uniqueFiles });
    }

    if (skippedDuplicates > 0) {
      appendConsole(`${skippedDuplicates} file ${skippedDuplicates === 1 ? 'gia presente in coda ignorato.' : 'gia presenti in coda ignorati.'}`);
    }
  }, [appendConsole]);

  const getProcessingDetails = (phaseText?: string) => {
    const rawPhase = String(phaseText || '').trim();
    if (!rawPhase) {
      return { title: 'Preparazione in corso', chunk: '' };
    }

    const chunkMatch = rawPhase.match(/\(([^)]+)\)/);
    const normalizedChunk = chunkMatch?.[1]
      ? chunkMatch[1].replace(/chunk\s+(\d+)\/(\d+)/i, 'Chunk $1 di $2')
      : '';

    const phaseWithoutChunk = rawPhase.replace(/\s*\([^)]*\)\s*/g, '').trim();
    const cleanedPhase = phaseWithoutChunk.replace(/^Fase\s*\d+\s*\/\s*\d+\s*:\s*/i, '').trim();
    const capitalizedPhase = cleanedPhase ? `${cleanedPhase.charAt(0).toUpperCase()}${cleanedPhase.slice(1)}` : 'Elaborazione';

    return {
      title: `${capitalizedPhase} in corso`,
      chunk: normalizedChunk,
    };
  };

  const resolveQueuedFilesForProcessing = useCallback(async () => {
    const api = window.pywebview?.api;
    const queuedFiles = filesRef.current.filter(file => file.status === 'queued' || file.status === 'done');

    if (queuedFiles.length === 0) {
      return [] as FileDescriptor[];
    }

    const resolvedFiles: FileDescriptor[] = [];

    for (const file of queuedFiles) {
      let nextPath = String(file.path || '').trim();
      let nextName = file.name;
      let nextSize = file.size;
      let nextDuration = file.duration;

      const sourceExists = nextPath && api?.check_path_exists
        ? Boolean((await api.check_path_exists(nextPath))?.exists)
        : Boolean(nextPath);

      if (!sourceExists) {
        if (!api?.ask_media_file) {
          appendConsole(`Impossibile ricollegare l'audio per ${file.name}.`);
          return null;
        }

        appendConsole(`Audio non trovato per ${file.name}. Selezionalo di nuovo per continuare.`);
        const selectedFile = await api.ask_media_file();

        if (!selectedFile?.path) {
          appendConsole(`Avvio annullato: audio non ricollegato per ${file.name}.`);
          return null;
        }

        nextPath = selectedFile.path;
        nextName = selectedFile.name;
        nextSize = selectedFile.size;
        nextDuration = selectedFile.duration || 0;

        dispatch({
          type: 'queue/update_source',
          id: file.id,
          path: nextPath,
          name: nextName,
          size: nextSize,
          duration: nextDuration,
        });
        appendConsole(`Audio ricollegato: ${nextName}`);
      }

      resolvedFiles.push({
        id: file.id,
        path: nextPath,
        name: nextName,
        size: nextSize,
        duration: nextDuration,
      });
    }

    return resolvedFiles;
  }, [appendConsole]);

  const startProcessing = async () => {
    if (queuedCount === 0 || !apiKey.trim()) return;
    if (window.pywebview?.api) {
      const fileDescriptors = await resolveQueuedFilesForProcessing();
      if (!fileDescriptors || fileDescriptors.length === 0) return;

      const result = await window.pywebview.api.start_processing?.(fileDescriptors, apiKey.trim(), true);
      if (!result?.ok) {
        appendConsole(`❌ ${result?.error || "Impossibile avviare l'elaborazione."}`);
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
      if (window.pywebview?.api?.answer_regenerate) {
        await window.pywebview.api.answer_regenerate(ans);
      }
    } catch (e) {
      console.error("Failed to send answer to Python:", e);
    }
  };

  const saveSettings = async () => {
    if (window.pywebview?.api) {
      const keys = fallbackKeys.split('\n').map(k => k.trim()).filter(Boolean);
      await window.pywebview.api.save_settings(apiKey.trim(), keys);
    }
    setIsSettingsOpen(false);
  };

  const handleExportDoc = useCallback(async () => {
    setIsExportMenuOpen(false);
    const html = editedContent;
    const docxTemplate = `<html><head><meta charset='utf-8'><title>${previewTitle || 'Sbobina'}</title></head><body>${html}</body></html>`;
    if (window.pywebview?.api?.export_docx) {
      const res = await window.pywebview.api.export_docx(`${previewTitle || 'Sbobina'}.docx`, docxTemplate);
      if (!res.ok && res.error !== "Annullato dall'utente") appendConsole(`❌ Errore salvataggio Word: ${res.error}`);
    } else {
      const blob = new Blob(['\ufeff', docxTemplate], { type: 'application/msword;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `${previewTitle || 'Sbobina'}.docx`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  }, [editedContent, previewTitle, appendConsole]);

  const handleExportPdf = useCallback(() => {
    setIsExportMenuOpen(false);
    const html = editedContent;
    const printWindow = document.createElement('iframe');
    printWindow.style.cssText = 'position:fixed;top:5vh;left:5vw;width:90vw;height:90vh;opacity:0;pointer-events:none;z-index:-1;';
    document.body.appendChild(printWindow);
    const styleLinks = Array.from(document.querySelectorAll('link[rel="stylesheet"], style')).map(el => el.outerHTML).join('\n');
    const doc = printWindow.contentWindow?.document;
    if (!doc) { document.body.removeChild(printWindow); return; }
    doc.open();
    doc.write(`<html><head><title>${previewTitle || 'Sbobina'}</title><meta charset="utf-8">${styleLinks}<style>body{padding:40px!important;background:white!important;color:black!important;}@media print{body{padding:0!important;}}</style></head><body><div class="prose prose-sm sm:prose-base max-w-none tiptap-editor">${html}</div><script>window.onload=()=>{setTimeout(()=>{window.print();setTimeout(()=>{window.parent.document.body.removeChild(window.frameElement);},1000);},750);};<\/script></body></html>`);
    doc.close();
  }, [editedContent, previewTitle]);

  const handleCopyForGoogleDocs = useCallback(async () => {
    setIsExportMenuOpen(false);
    const normalizedHtml = normalizePreviewHtmlContent(editedContent);
    const temp = document.createElement('div');
    temp.innerHTML = normalizedHtml;
    try {
      const htmlBlob = new Blob([normalizedHtml], { type: 'text/html' });
      const textBlob = new Blob([temp.textContent || temp.innerText || ''], { type: 'text/plain' });
      await navigator.clipboard.write([new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob })]);
    } catch (_) {
      navigator.clipboard.writeText(temp.textContent || temp.innerText || '');
    }
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  }, [editedContent]);

  const handleAudioStateChange = useCallback(({ currentTime, playbackRate, volume }: { currentTime: number; playbackRate: number; volume: number }) => {
    currentEditorSessionRef.current = { ...currentEditorSessionRef.current, audioTime: currentTime, playbackRate, volume };
  }, []);

  const handleScrollTopChange = useCallback((scrollTop: number) => {
    currentEditorSessionRef.current = { ...currentEditorSessionRef.current, scrollTop };
  }, []);

  const closePreview = useCallback(() => {
    const sessionKey = currentPreviewSessionKeyRef.current;
    if (sessionKey) {
      const session = currentEditorSessionRef.current;
      const hasData = session.audioTime !== undefined || session.playbackRate !== undefined || session.volume !== undefined || session.scrollTop !== undefined;
      if (hasData) saveEditorSession(sessionKey, session);
    }
    currentEditorSessionRef.current = {};
    currentPreviewSessionKeyRef.current = null;
    setIsExportMenuOpen(false);
    setPreviewContent(null);
    setEditedContent('');
    setPreviewTitle('');
    setPreviewPath('');
    setPreviewFileId(null);
    setPreviewSourcePath('');
    setAudioSrc(null);
    setAudioRelinkNeeded(false);
    setIsCopied(false);
    setAutosaveStatus('idle');
    lastPersistedPreviewRef.current = '';
  }, []);

  const runEnvironmentValidation = async () => {
    if (!window.pywebview?.api?.validate_environment) return;
    setIsValidatingEnvironment(true);
    try {
      const response = await window.pywebview.api.validate_environment(apiKey.trim(), Boolean(apiKey.trim()));
      if (!response?.ok || !response.result) {
        appendConsole(`❌ Validazione ambiente fallita: ${response?.error || 'errore sconosciuto'}`);
        setValidationResult(null);
        return;
      }
      setValidationResult(response.result);
      appendConsole(response.result.summary);
    } catch (error: any) {
      appendConsole(`❌ Validazione ambiente fallita: ${error?.message || error}`);
      setValidationResult(null);
    } finally {
      setIsValidatingEnvironment(false);
    }
  };

  const openFile = async (path: string) => {
    if (window.pywebview?.api) await window.pywebview.api.open_file(path);
  };

  const loadPreviewAudio = useCallback(async (sourcePath?: string) => {
    const normalizedSource = String(sourcePath || '').trim();
    if (!normalizedSource || !window.pywebview?.api?.stream_media_file) {
      setAudioSrc(null);
      setAudioRelinkNeeded(Boolean(normalizedSource));
      return;
    }

    const streamRes = await window.pywebview.api.stream_media_file(normalizedSource);
    if (streamRes.ok && streamRes.url) {
      setAudioSrc(streamRes.url);
      setAudioRelinkNeeded(false);
      return;
    }

    setAudioSrc(null);
    setAudioRelinkNeeded(true);
  }, []);

  const relinkPreviewAudio = useCallback(async () => {
    if (!window.pywebview?.api?.ask_media_file || !previewFileId) return;
    try {
      const selectedFile = await window.pywebview.api.ask_media_file();
      if (!selectedFile?.path) return;

      dispatch({
        type: 'queue/update_source',
        id: previewFileId,
        path: selectedFile.path,
        name: selectedFile.name,
        size: selectedFile.size,
        duration: selectedFile.duration,
      });
      setPreviewSourcePath(selectedFile.path);
      await loadPreviewAudio(selectedFile.path);
      appendConsole(`Audio ricollegato: ${selectedFile.name}`);
    } catch (error: any) {
      appendConsole(`❌ Impossibile ricollegare l'audio: ${error?.message || error}`);
    }
  }, [appendConsole, loadPreviewAudio, previewFileId]);

  const openPreview = async (htmlPath: string, filename: string, sourcePath?: string, fileId?: string) => {
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
          setPreviewInitAudio({ time: savedSession.audioTime, playbackRate: savedSession.playbackRate, volume: savedSession.volume });
          setPreviewInitScrollTop(savedSession.scrollTop);

          setPreviewContent(safeContent);
          setEditedContent(safeContent);
          setPreviewTitle(filename);
          setPreviewPath(htmlPath);
          setPreviewFileId(fileId ?? null);
          setPreviewSourcePath(sourcePath || '');
          setIsCopied(false);
          setAutosaveStatus('idle');
          lastPersistedPreviewRef.current = safeContent;
          await loadPreviewAudio(sourcePath);
        } else {
          appendConsole(`❌ Errore anteprima: ${res.error}`);
        }
      } catch (e: any) {
        appendConsole(`❌ Errore JS anteprima: ${e.message || e}`);
      }
    } else {
      appendConsole('❌ Funzione anteprima non disponibile in questa versione.');
    }
  };

  const queuedCount = files.filter(f => f.status === 'queued').length;
  const doneCount = files.filter(f => f.status === 'done').length;
  const processingCount = files.filter(f => f.status === 'processing').length;
  const hasApiKey = Boolean(apiKey.trim());
  const isReplacementKeyValid = GEMINI_KEY_PATTERN.test(newKeyInput.trim());
  const canStart = queuedCount > 0 && hasApiKey;
  const shouldShowActionPanel = appState !== 'idle' || queuedCount > 0;
  const lastConsoleMessage = consoleLogs.length > 0 ? consoleLogs[consoleLogs.length - 1] : 'Pronto per iniziare.';

  // --- Title gradient style ---
  const titleGradient = { background: 'linear-gradient(90deg, var(--gradient-title-from), var(--gradient-title-to))', WebkitBackgroundClip: 'text' as const, WebkitTextFillColor: 'transparent' };
  const sGradient = { background: 'linear-gradient(90deg, var(--gradient-s-from), var(--gradient-s-to))', WebkitBackgroundClip: 'text' as const, WebkitTextFillColor: 'transparent' };

  useEffect(() => {
    if (!previewPath || previewContent === null) return;
    if (editedContent === lastPersistedPreviewRef.current) return;

    setAutosaveStatus('saving');
    const timeoutId = window.setTimeout(async () => {
      if (!window.pywebview?.api?.save_html_content) return;
      const contentToSave = normalizePreviewHtmlContent(editedContent);
      const res = await window.pywebview.api.save_html_content(previewPath, contentToSave);
      if (res.ok) {
        lastPersistedPreviewRef.current = contentToSave;
        setPreviewContent(contentToSave);
        setAutosaveStatus('saved');
      } else {
        setAutosaveStatus('error');
      }
    }, 700);

    return () => window.clearTimeout(timeoutId);
  }, [editedContent, previewContent, previewPath]);

  useEffect(() => {
    if (autosaveStatus !== 'saved') return;
    const timeoutId = window.setTimeout(() => setAutosaveStatus('idle'), 1500);
    return () => window.clearTimeout(timeoutId);
  }, [autosaveStatus]);

  useEffect(() => {
    if (previewContent === null) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closePreview();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [previewContent, closePreview]);

  useEffect(() => {
    if (!isExportMenuOpen) return;
    const handlePointerDown = (e: PointerEvent) => {
      if (!exportMenuRef.current?.contains(e.target as Node)) setIsExportMenuOpen(false);
    };
    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [isExportMenuOpen]);

  return (
    <div className="app-shell min-h-screen font-sans flex flex-col" style={{ background: 'var(--bg-base)', color: 'var(--text-secondary)' }}>
      
      {/* Top Navigation */}
      <header className="sticky top-0 z-40 backdrop-blur-2xl" style={{ borderBottom: '1px solid var(--border-subtle)', background: 'rgba(16, 13, 11, 0.08)' }}>
        <div className="max-w-6xl mx-auto px-5 sm:px-6 min-h-[84px] flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
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
                <span className="inline-flex h-2.5 w-2.5 rounded-full animate-pulse" style={{ background: 'var(--processing-dot)' }} />
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
              className="icon-button"
              aria-label={themeMode === 'dark' ? 'Attiva tema chiaro' : 'Attiva tema scuro'}
              title={themeMode === 'dark' ? 'Tema chiaro' : 'Tema scuro'}
            >
              {themeMode === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>
            <button onClick={() => setIsSettingsOpen(true)} className="icon-button" aria-label="Apri impostazioni">
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
                  onClick={() => {
                    try { window.localStorage.setItem(UPDATE_DISMISSED_KEY, updateAvailable); } catch (_) {}
                    setUpdateAvailable(null);
                  }}
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

      <main className="max-w-6xl mx-auto px-5 sm:px-6 py-8 w-full flex-1 flex flex-col gap-6">
        
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
              {files.length > 0 && (
                <span className="status-pill self-start sm:self-auto shrink-0 whitespace-nowrap">
                  <span className="sm:hidden">{files.length} / {doneCount}</span>
                  <span className="hidden sm:inline">
                    {files.length} {files.length === 1 ? 'elemento' : 'elementi'}{doneCount > 0 ? ` / ${doneCount} completat${doneCount !== 1 ? 'i' : 'o'}` : ''}
                  </span>
                </span>
              )}
            </div>
            <div className="flex flex-col items-end gap-2">
              <AnimatePresence>
                {files.length > 0 && appState === 'idle' && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center justify-end gap-2 self-end">
                    <button onClick={clearAllFiles} className="premium-button-secondary compact-button" style={{ color: 'var(--error-text)', borderColor: 'var(--error-ring)', background: 'var(--error-subtle)' }}>
                      Svuota tutto
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          <AnimatePresence mode="popLayout">
            {files.length === 0 && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="p-10 rounded-[26px] text-center flex flex-col items-center border border-dashed"
                style={{ borderColor: 'var(--border-default)', background: 'rgba(255,255,255,0.03)' }}>
                <div className="w-14 h-14 rounded-[20px] flex items-center justify-center mb-4" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-default)' }}>
                  <FileText className="w-5 h-5" style={{ color: 'var(--text-faint)' }} />
                </div>
                <p className="text-sm leading-6 max-w-md" style={{ color: 'var(--text-muted)' }}>Nessun file in coda. Aggiungi un file per iniziare.</p>
              </motion.div>
            )}

            {files.map((file, idx) => {
              const processingDetails = file.status === 'processing' ? getProcessingDetails(currentPhase) : null;
              return (
              <motion.div
                key={file.id}
                layout="position"
                initial={{ opacity: 0, y: 20, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98, transition: { duration: 0.18 } }}
                transition={{
                  opacity: { duration: 0.18, ease: 'easeOut' },
                  scale: { duration: 0.2, ease: 'easeOut' },
                  y: { duration: 0.2, ease: 'easeOut' },
                  layout: { duration: 0.24, ease: [0.22, 1, 0.36, 1] },
                }}
                className={`queue-card relative transition-colors ${file.status === 'processing' ? 'processing-card px-5 py-4' : 'p-5'}`}
                style={{
                  border: `1px solid ${
                    file.status === 'processing'
                      ? 'var(--processing-ring)'
                      : file.status === 'done'
                        ? 'var(--success-ring)'
                        : file.status === 'error'
                          ? 'var(--error-ring)'
                          : 'var(--card-queued-border)'
                  }`,
                  background: file.status === 'processing'
                    ? 'linear-gradient(180deg, rgba(255,255,255,0.02), var(--processing-bg))'
                    : file.status === 'done'
                      ? 'linear-gradient(135deg, var(--success-subtle), rgba(255,255,255,0.02))'
                      : file.status === 'error'
                        ? 'linear-gradient(135deg, var(--error-subtle), rgba(255,255,255,0.02))'
                        : 'var(--card-queued-bg)',
                }}>
                <div className="relative z-10 flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3 overflow-hidden flex-1">
                    <div className={`${file.status === 'processing' ? 'w-11 h-11 rounded-[16px]' : 'w-12 h-12 rounded-[18px]'} flex items-center justify-center shrink-0`} style={{
                      background: file.status === 'done'
                        ? 'var(--success-subtle)'
                        : file.status === 'processing'
                          ? 'var(--processing-bg)'
                          : file.status === 'error'
                            ? 'var(--error-subtle)'
                            : 'rgba(255,255,255,0.03)',
                      color: file.status === 'done'
                        ? 'var(--success-text)'
                        : file.status === 'processing'
                          ? 'var(--processing-text)'
                          : file.status === 'error'
                            ? 'var(--error-text)'
                            : 'var(--text-muted)',
                    }}>
                      {file.status === 'done'
                        ? <CheckCircle className="w-5 h-5" />
                        : file.status === 'processing'
                          ? <Clock className="w-5 h-5 animate-pulse" />
                          : file.status === 'error'
                            ? <AlertCircle className="w-5 h-5" />
                            : <FileAudio className="w-5 h-5" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h4 className="text-base font-semibold truncate tracking-tight" style={{ color: 'var(--text-primary)' }}>{file.name}</h4>
                      <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
                        <span>{formatSize(file.size)}</span>
                        {file.duration > 0 && <><span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} /><span>{formatDuration(file.duration)}</span></>}
                        {file.status === 'done' && <><span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} /><span style={{ color: 'var(--success-text)' }}>Completato</span></>}
                        {file.status === 'error' && <><span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} /><span style={{ color: 'var(--error-text)' }}>{file.errorText || 'Errore'}</span></>}
                      </div>
                      {file.status === 'processing' && processingDetails && (
                        <motion.div
                          layout="position"
                          className="mt-2 flex min-h-7 flex-wrap items-center gap-1.5"
                          transition={{ layout: { duration: 0.2, ease: [0.22, 1, 0.36, 1] } }}
                        >
                          <span className="helper-chip processing-chip processing-chip-compact">
                            <span className="inline-flex h-2 w-2 rounded-full animate-pulse" style={{ background: 'var(--processing-dot)' }} />
                            In elaborazione
                          </span>
                          <AnimatePresence mode="wait" initial={false}>
                            <motion.span
                              key={`processing-title-${processingDetails.title}`}
                              initial={{ opacity: 0, y: 4 }}
                              animate={{ opacity: 1, y: 0 }}
                              exit={{ opacity: 0, y: -4 }}
                              transition={{ duration: 0.16, ease: 'easeOut' }}
                              className="text-[0.96rem] font-semibold tracking-tight"
                              style={{ color: 'var(--text-primary)' }}
                            >
                              {processingDetails.title}
                            </motion.span>
                          </AnimatePresence>
                          <AnimatePresence mode="wait" initial={false}>
                            {processingDetails.chunk && (
                              <motion.span
                                key={`processing-chunk-${processingDetails.chunk}`}
                                initial={{ opacity: 0, y: 4 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -4 }}
                                transition={{ duration: 0.16, ease: 'easeOut' }}
                                className="text-[11px] font-medium leading-none self-center"
                                style={{ color: 'var(--processing-text)' }}
                              >
                                {processingDetails.chunk}
                              </motion.span>
                            )}
                          </AnimatePresence>
                        </motion.div>
                      )}
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2 shrink-0">
                    {file.status === 'done' && file.outputHtml && (
                      <>
                        <button onClick={(e) => { e.stopPropagation(); openPreview(file.outputHtml!, file.name, file.path, file.id); }} className="icon-button compact-icon-button" style={{ color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.03)', borderColor: 'var(--border-default)' }} title="Anteprima testo"><Eye className="w-4 h-4" /></button>
                        <button onClick={(e) => { e.stopPropagation(); openFile(file.outputHtml!); }} className="icon-button compact-icon-button" style={{ color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.03)', borderColor: 'var(--border-default)' }} title="Apri nel browser"><ExternalLink className="w-4 h-4" /></button>
                        {file.outputDir && <button onClick={(e) => { e.stopPropagation(); openFile(file.outputDir!); }} className="icon-button compact-icon-button" style={{ color: 'var(--text-muted)' }} title="Apri cartella"><FolderOpen className="w-4 h-4" /></button>}
                      </>
                    )}
                    {appState !== 'processing' && (
                      <>
                        {file.status === 'queued' && (
                          <>
                            <button onClick={() => moveFile(file.id, 'up')} disabled={idx === 0} className="icon-button compact-icon-button disabled:opacity-30" style={{ color: 'var(--text-muted)' }}><ChevronUp className="w-4 h-4" /></button>
                            <button onClick={() => moveFile(file.id, 'down')} disabled={idx === files.length - 1} className="icon-button compact-icon-button disabled:opacity-30" style={{ color: 'var(--text-muted)' }}><ChevronDown className="w-4 h-4" /></button>
                          </>
                        )}
                        <button onClick={() => removeFile(file.id)} className="icon-button compact-icon-button" style={{ color: 'var(--error-text)', borderColor: 'var(--error-ring)', background: 'var(--error-subtle)' }}><Trash2 className="w-4 h-4" /></button>
                      </>
                    )}
                  </div>
                </div>

                {file.status === 'processing' && (
                  <div className="relative z-10 mt-3">
                    <div className="flex items-center justify-between gap-3 mb-1.5 text-[10px] font-medium uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
                      <span>Generazione sbobina</span>
                      <span style={{ color: 'var(--text-primary)' }}>{file.progress}%</span>
                    </div>
                    <div className="processing-progress h-2 w-full rounded-full overflow-hidden" style={{ background: 'var(--progress-bg)' }}>
                      <motion.div className="processing-progress-fill h-full rounded-full" style={{ background: 'linear-gradient(90deg, var(--accent-gradient-start), var(--accent-gradient-end))' }} initial={{ width: 0 }} animate={{ width: `${file.progress}%` }} transition={{ ease: "linear", duration: 0.3 }} />
                    </div>
                    <div className="flex justify-between mt-1.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                      <span>Generazione in corso</span>
                      {processingDetails?.chunk ? <span>{processingDetails.chunk}</span> : <span>Avanzamento attivo</span>}
                    </div>
                  </div>
                )}
              </motion.div>
              );
            })}
          </AnimatePresence>
        </div>

        {/* Console */}
        <div className="console-shell console-shell-subtle">
          <div className="px-5 py-3 flex items-center justify-between" style={{ background: 'var(--console-header)', borderBottom: '1px solid var(--border-subtle)' }}>
            <h2 className="text-xs font-semibold uppercase tracking-wider flex items-center gap-2" style={{ color: 'var(--text-muted)' }}>
              <span className={`w-2.5 h-2.5 rounded-full ${appState === 'processing' ? 'animate-pulse' : ''}`} style={appState !== 'processing' ? { background: 'var(--text-faint)' } : { background: 'var(--processing-dot)' }} />
              Console
            </h2>
            <div className="flex items-center gap-2">
              <button onClick={() => setConsoleLogs([])} className="premium-button-secondary compact-button px-2.5 py-1.5 text-[11px] rounded-[13px]" style={{ background: 'rgba(255,255,255,0.02)', borderColor: 'var(--border-default)' }}>
                Pulisci
              </button>
              <button onClick={() => setIsConsoleExpanded(prev => !prev)} className="premium-button-secondary compact-button px-2.5 py-1.5 text-[11px] rounded-[13px]" style={{ background: 'rgba(255,255,255,0.02)', borderColor: 'var(--border-default)' }}>
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
            <div ref={consoleEndRef} />
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
                  {!hasApiKey ? 'Inserisci API Key nelle impostazioni' : `Avvia sbobinatura (${queuedCount} file)`}
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
                <button disabled
                  className="premium-button w-full text-lg opacity-70"
                  style={{ background: 'var(--btn-disabled-bg)', color: 'var(--btn-disabled-text)', cursor: 'wait' }}>
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
      <footer className="max-w-6xl mx-auto w-full px-5 sm:px-6 pb-8 pt-2 flex items-center justify-center gap-3 text-sm shrink-0" style={{ color: 'var(--text-muted)' }}>
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
          style={{ color: 'var(--text-muted)' }}
        >
          Supporta il progetto su Ko-fi ☕
        </a>
      </footer>

      {/* Regenerate Modal */}
      <AnimatePresence>
        {regeneratePrompt && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => handleRegenerateAnswer(false)} className="absolute inset-0" style={{ background: 'var(--bg-overlay)', backdropFilter: 'blur(10px)' }} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="modal-card relative w-full max-w-md max-h-[86vh] overflow-hidden flex flex-col">
              <div className="flex items-center justify-between gap-3 px-5 py-4 shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <div className="flex items-center gap-3 min-w-0">
                  <AlertCircle className="w-5 h-5 shrink-0" style={{ color: 'var(--warning-text)' }} />
                  <h2 className="text-lg font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
                    {regeneratePrompt.mode === 'completed' ? 'Versione già pronta' : 'Ripresa disponibile'}
                  </h2>
                </div>
                <button onClick={() => handleRegenerateAnswer(false)} className="icon-button h-10 w-10 rounded-[14px]" style={{ color: 'var(--text-muted)' }} aria-label="Chiudi finestra">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4 text-sm" style={{ color: 'var(--text-secondary)' }}>
                <p>
                  {regeneratePrompt.mode === 'completed'
                    ? <>Il file <strong style={{ color: 'var(--text-primary)' }}>{regeneratePrompt.filename}</strong> risulta già completato.</>
                    : <>Per il file <strong style={{ color: 'var(--text-primary)' }}>{regeneratePrompt.filename}</strong> ci sono progressi salvati e pronti per essere ripresi.</>}
                </p>
                <p>
                  {regeneratePrompt.mode === 'completed'
                    ? 'Puoi usare la versione già pronta oppure rigenerare tutto da zero.'
                    : 'Puoi riprendere da dove eri rimasto oppure ricominciare da zero perdendo i progressi salvati.'}
                </p>
              </div>
              <div className="px-5 py-4 flex gap-3 shrink-0" style={{ background: 'var(--bg-elevated)', borderTop: '1px solid var(--border-subtle)' }}>
                <button 
                  onClick={() => handleRegenerateAnswer(false)} 
                  className="premium-button-secondary flex-1 justify-center"
                >
                  {regeneratePrompt.mode === 'completed' ? 'Usa versione pronta' : 'Riprendi da dove eri rimasto'}
                </button>
                <button 
                  onClick={() => handleRegenerateAnswer(true)} 
                  className="premium-button flex-1 justify-center"
                >
                  {regeneratePrompt.mode === 'completed' ? 'Rigenera da zero' : 'Ricomincia da zero'}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Ask New Key Modal */}
      <AnimatePresence>
        {askNewKeyPrompt && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => {
              if (window.pywebview?.api?.answer_new_key) {
                window.pywebview.api.answer_new_key(null);
              }
              setAskNewKeyPrompt(false);
            }} className="absolute inset-0" style={{ background: 'var(--bg-overlay)', backdropFilter: 'blur(10px)' }} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="modal-card relative w-full max-w-md max-h-[86vh] overflow-hidden flex flex-col">
              <div className="flex items-center justify-between gap-3 px-5 py-4 shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <div className="flex items-center gap-3 min-w-0">
                  <Key className="w-5 h-5 shrink-0" style={{ color: 'var(--warning-text)' }} />
                  <h2 className="text-lg font-semibold truncate" style={{ color: 'var(--text-primary)' }}>Esaurimento quota</h2>
                </div>
                <button onClick={() => {
                  if (window.pywebview?.api?.answer_new_key) {
                    window.pywebview.api.answer_new_key(null);
                  }
                  setAskNewKeyPrompt(false);
                }} className="icon-button h-10 w-10 rounded-[14px]" style={{ color: 'var(--text-muted)' }} aria-label="Chiudi finestra">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4 text-sm" style={{ color: 'var(--text-secondary)' }}>
                <p>
                  La quota del tuo account Google per le API Gemini sembra esaurita (o temporaneamente limitata).
                </p>
                <p>
                  Se hai un'altra API Key con quota disponibile, incollala qui per continuare da dove eri rimasto, senza perdere i progressi.
                </p>
                <div className="pt-2 space-y-2">
                  <input 
                    type="password"
                    value={newKeyInput}
                    onChange={(e) => setNewKeyInput(e.target.value)}
                    placeholder="Incolla qui la nuova API Key..."
                    className="app-input font-mono text-sm"
                    style={{ background: 'var(--bg-input)', color: 'var(--text-primary)' }}
                  />
                  <p className="text-xs" style={{ color: newKeyInput.trim().length === 0 || isReplacementKeyValid ? 'var(--text-muted)' : 'var(--error-text)' }}>
                    {newKeyInput.trim().length === 0
                      ? 'Inserisci una chiave Gemini valida per continuare.'
                      : isReplacementKeyValid
                        ? 'Formato chiave valido.'
                        : 'La chiave non sembra valida. Deve iniziare con AIza.'}
                  </p>
                </div>
              </div>
              <div className="px-5 py-4 flex flex-col gap-3 shrink-0" style={{ background: 'var(--bg-elevated)', borderTop: '1px solid var(--border-subtle)' }}>
                <button 
                  onClick={() => {
                    if (!isReplacementKeyValid) return;
                    if (window.pywebview?.api?.answer_new_key) {
                      window.pywebview.api.answer_new_key(newKeyInput.trim());
                    }
                    setAskNewKeyPrompt(false);
                  }} 
                  className="premium-button w-full" 
                  disabled={!isReplacementKeyValid}
                >
                  Continua
                </button>
                <button 
                  onClick={() => {
                    if (window.pywebview?.api?.answer_new_key) {
                      window.pywebview.api.answer_new_key(null);
                    }
                    setAskNewKeyPrompt(false);
                  }} 
                  className="premium-button-secondary w-full"
                >
                  Annulla
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Settings Modal */}
      <AnimatePresence>
        {isSettingsOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setIsSettingsOpen(false)} className="absolute inset-0" style={{ background: 'var(--bg-overlay)', backdropFilter: 'blur(10px)' }} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="modal-card relative w-full max-w-md max-h-[86vh] overflow-hidden flex flex-col">
              <div className="flex items-center justify-between px-5 py-4 shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
                  <Settings className="w-5 h-5" style={{ color: 'var(--text-muted)' }} /> Impostazioni
                </h2>
                <button onClick={() => setIsSettingsOpen(false)} className="icon-button h-10 w-10 rounded-[14px]" style={{ color: 'var(--text-muted)' }} aria-label="Chiudi impostazioni"><X className="w-4 h-4" /></button>
              </div>
              <div className="app-scroll flex-1 overflow-y-auto overflow-x-hidden px-5 py-5 space-y-6">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>Google Gemini API Key (Principale)</label>
                    <button onClick={() => setShowApiKeys(!showApiKeys)} className="icon-button h-9 w-9" style={{ color: 'var(--text-muted)' }} title={showApiKeys ? "Nascondi chiave" : "Mostra chiave"}>
                      {showApiKeys ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <input type={showApiKeys ? "text" : "password"} value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="AIzaSy..."
                    className="app-input font-mono text-sm"
                    style={{ background: 'var(--bg-input)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }} />
                  <p className="text-xs mt-2 flex items-start gap-1.5" style={{ color: 'var(--text-muted)' }}>
                    <AlertCircle className="w-4 h-4 shrink-0" /> Salvata in modo sicuro tramite DPAPI (Windows) o Keyring (Mac/Linux).
                  </p>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>API Keys di Riserva (Fallback)</label>
                    <button onClick={() => setShowApiKeys(!showApiKeys)} className="icon-button h-9 w-9" style={{ color: 'var(--text-muted)' }} title={showApiKeys ? "Nascondi chiavi" : "Mostra chiavi"}>
                      {showApiKeys ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <textarea value={fallbackKeys} onChange={e => setFallbackKeys(e.target.value)} placeholder="Inserisci una API Key per riga..." rows={3}
                    className={`app-textarea font-mono text-sm ${!showApiKeys ? 'obscured-text' : ''}`}
                    style={{ background: 'var(--bg-input)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }} />
                  <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>Usate automaticamente in caso di esaurimento quota (429).</p>
                </div>
                <div className="pt-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-muted)' }}>Avanzate (Sola Lettura)</h3>
                  <ul className="space-y-2 text-sm" style={{ color: 'var(--text-muted)' }}>
                    <li className="flex justify-between"><span>Modello:</span> <span style={{ color: 'var(--text-secondary)' }}>gemini-2.5-flash</span></li>
                    <li className="flex justify-between"><span>Chunk:</span> <span style={{ color: 'var(--text-secondary)' }}>15 minuti</span></li>
                    <li className="flex justify-between"><span>Overlap:</span> <span style={{ color: 'var(--text-secondary)' }}>30 secondi</span></li>
                    <li className="flex justify-between"><span>Pre-conversione:</span> <span style={{ color: 'var(--text-secondary)' }}>Mono 16kHz 48k</span></li>
                  </ul>
                </div>
                <div className="pt-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>Validate Environment</h3>
                    <button
                      onClick={runEnvironmentValidation}
                      disabled={isValidatingEnvironment}
                      className="premium-button-secondary compact-button px-3 py-1.5 text-[11px] rounded-[13px]"
                      style={{ background: 'rgba(255,255,255,0.02)', color: 'var(--text-primary)', borderColor: 'var(--border-default)' }}
                    >
                      {isValidatingEnvironment ? 'Verifica...' : 'Verifica ambiente'}
                    </button>
                  </div>
                  {validationResult && (
                    <div className="space-y-2 text-sm">
                      <p style={{ color: validationResult.ok ? 'var(--success-text)' : 'var(--error-text)' }}>{validationResult.summary}</p>
                      {validationResult.checks.map(check => (
                        <div key={check.id} className="rounded-lg px-3 py-2 overflow-hidden" style={{ background: 'var(--bg-input)', border: '1px solid var(--border-subtle)' }}>
                          <div className="flex items-center justify-between gap-3">
                            <span style={{ color: 'var(--text-primary)' }}>{check.label}</span>
                            <span style={{ color: check.status === 'ok' ? 'var(--success-text)' : check.status === 'warning' ? 'var(--warning-text)' : 'var(--error-text)' }}>
                              {check.status.toUpperCase()}
                            </span>
                          </div>
                          <p className="mt-1" style={{ color: 'var(--text-secondary)' }}>{check.message}</p>
                          {check.details && <p className="mt-1 text-xs font-mono break-all whitespace-pre-wrap" style={{ color: 'var(--text-muted)', overflowWrap: 'anywhere' }}>{check.details}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <div className="px-5 py-4 shrink-0" style={{ background: 'var(--bg-elevated)', borderTop: '1px solid var(--border-subtle)' }}>
                <button onClick={saveSettings} className="w-full py-3 font-medium rounded-xl transition-colors" style={{ background: 'var(--btn-primary-bg)', color: 'var(--btn-primary-text)' }}>Salva e Chiudi</button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Preview Modal */}
      <AnimatePresence>
        {previewContent !== null && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closePreview}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
            style={{ background: 'var(--bg-overlay)', backdropFilter: 'blur(10px)' }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              onClick={event => event.stopPropagation()}
              className="modal-card w-full max-w-5xl max-h-[88vh] flex flex-col overflow-hidden"
            >
              <div className="px-4 py-4 sm:px-5 flex items-center justify-between gap-3 border-b shrink-0" style={{ borderColor: 'var(--border-subtle)' }}>
                <h3 className="font-semibold text-lg flex items-center gap-2 truncate min-w-0" style={{ color: 'var(--text-primary)' }}>
                  <FileText className="w-5 h-5 shrink-0" style={{ color: 'var(--text-muted)' }} />
                  <span className="truncate">Anteprima: {previewTitle}</span>
                </h3>
                <div className="flex gap-2 shrink-0 flex-wrap justify-end">
                  <span className="inline-flex h-11 items-center rounded-[14px] px-3 text-sm font-medium" style={{ color: autosaveStatus === 'error' ? 'var(--error-text)' : autosaveStatus === 'saved' ? 'var(--success-text)' : 'var(--text-muted)', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-default)' }}>
                    {autosaveStatus === 'saving' ? 'Salvataggio...' : autosaveStatus === 'saved' ? 'Salvato' : autosaveStatus === 'error' ? 'Errore salvataggio' : 'Salvataggio automatico'}
                  </span>
                  <div className="relative" ref={exportMenuRef}>
                    <button
                      onClick={() => setIsExportMenuOpen(prev => !prev)}
                      className="premium-button-secondary h-11 rounded-[14px] px-4 text-sm flex items-center gap-2"
                      style={isExportMenuOpen ? { borderColor: 'var(--accent-bg)', color: 'var(--text-primary)' } : undefined}
                    >
                      <FileText className="w-4 h-4" />
                      Esporta
                      <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-150 ${isExportMenuOpen ? 'rotate-180' : ''}`} />
                    </button>
                    {isExportMenuOpen && (
                      <div
                        className="absolute right-0 top-full mt-1.5 z-[60] rounded-xl overflow-hidden"
                        style={{ minWidth: '210px', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', boxShadow: '0 16px 40px rgba(0,0,0,0.28)' }}
                      >
                        <button onClick={handleExportDoc} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors hover:bg-white/5" style={{ color: 'var(--text-primary)' }}>
                          <FileText className="w-4 h-4 shrink-0" style={{ color: 'var(--text-muted)' }} />
                          <div>
                            <div className="font-medium">Word (.docx)</div>
                            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Salva come documento</div>
                          </div>
                        </button>
                        <button onClick={handleExportPdf} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors hover:bg-white/5" style={{ color: 'var(--text-primary)' }}>
                          <Printer className="w-4 h-4 shrink-0" style={{ color: 'var(--text-muted)' }} />
                          <div>
                            <div className="font-medium">PDF / Stampa</div>
                            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Apri dialogo di stampa</div>
                          </div>
                        </button>
                        <div style={{ height: '1px', background: 'var(--border-subtle)', margin: '4px 0' }} />
                        <button onClick={handleCopyForGoogleDocs} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors hover:bg-white/5" style={{ color: isCopied ? 'var(--success-text)' : 'var(--text-primary)' }}>
                          {isCopied ? <Check className="w-4 h-4 shrink-0" /> : <Copy className="w-4 h-4 shrink-0" style={{ color: 'var(--text-muted)' }} />}
                          <div>
                            <div className="font-medium">{isCopied ? 'Copiato!' : 'Copia per Google Docs'}</div>
                            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Incolla in Google Docs</div>
                          </div>
                        </button>
                      </div>
                    )}
                  </div>
                  <button onClick={closePreview} className="icon-button h-11 w-11 rounded-[14px]" style={{ color: 'var(--text-muted)' }}>
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>

              <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
                <Suspense fallback={<div className="p-6 text-sm" style={{ color: 'var(--text-muted)' }}>Caricamento editor...</div>}>
                  <LazyRichTextEditor initialContent={previewContent || ''} onChange={setEditedContent} initialScrollTop={previewInitScrollTop} onScrollTopChange={handleScrollTopChange} />
                </Suspense>
              </div>

              {(audioSrc || audioRelinkNeeded) && (
                <div className="shrink-0 border-t px-4 sm:px-5" style={{ borderColor: 'var(--border-subtle)' }}>
                  {audioSrc ? (
                    <Suspense fallback={<div className="p-4 text-sm" style={{ color: 'var(--text-muted)' }}>Caricamento player...</div>}>
                      <LazyAudioPlayer src={audioSrc} initialTime={previewInitAudio.time} initialPlaybackRate={previewInitAudio.playbackRate} initialVolume={previewInitAudio.volume} onStateChange={handleAudioStateChange} />
                    </Suspense>
                  ) : (
                    <div className="flex items-center justify-between gap-3 py-3.5">
                      <div className="min-w-0">
                        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Audio non trovato</p>
                        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                          Il file originale e stato spostato. Selezionalo di nuovo per riattivare il player.
                        </p>
                      </div>
                      <button onClick={relinkPreviewAudio} className="premium-button-secondary compact-button shrink-0">
                        Ricollega audio
                      </button>
                    </div>
                  )}
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
}

