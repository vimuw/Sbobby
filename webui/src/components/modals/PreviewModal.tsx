import React, { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Check, Copy, ExternalLink, FileText, X } from 'lucide-react';
import type { Heading } from '../RichTextEditor';
import { normalizePreviewHtmlContent } from '../../previewHtml';

const LazyAudioPlayer = React.lazy(() => import('../AudioPlayer').then(module => ({ default: module.AudioPlayer })));
const LazyRichTextEditor = React.lazy(() => import('../RichTextEditor').then(module => ({ default: module.RichTextEditor })));

interface PreviewModalProps {
  previewContent: string | null;
  previewTitle: string;
  htmlPath: string;
  onClose: () => void;
  audioSrc: string | null;
  audioRelinkNeeded: boolean;
  onRelink: () => Promise<boolean | undefined>;
  previewInitAudio: { time?: number; playbackRate?: number; volume?: number };
  previewInitScrollTop: number | undefined;
  onAudioStateChange: (state: { currentTime: number; playbackRate: number; volume: number }) => void;
  onScrollTopChange: (scrollTop: number) => void;
}

export function PreviewModal({
  previewContent, previewTitle, htmlPath, onClose,
  audioSrc, audioRelinkNeeded, onRelink,
  previewInitAudio, previewInitScrollTop,
  onAudioStateChange, onScrollTopChange,
}: PreviewModalProps) {
  const [isTocOpen, setIsTocOpen] = useState(false);
  const [headings, setHeadings] = useState<Heading[]>([]);
  const [isCopied, setIsCopied] = useState(false);
  const [relinkSuccess, setRelinkSuccess] = useState(false);
  const [isRelinking, setIsRelinking] = useState(false);
  const relinkTimerRef = useRef<number | null>(null);
  const [autosaveStatus, setAutosaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const getHtmlRef = useRef<(() => string) | null>(null);
  const isDirtyRef = useRef(false);
  const lastPersistedRef = useRef(previewContent ?? '');
  const autosaveTimerRef = useRef<number | null>(null);
  const autosaveGenRef = useRef(0);
  const saveErrorOnCloseRef = useRef(false);
  const htmlPathRef = useRef(htmlPath);
  useEffect(() => { htmlPathRef.current = htmlPath; }, [htmlPath]);
  useEffect(() => {
    lastPersistedRef.current = previewContent ?? '';
    isDirtyRef.current = false;
    saveErrorOnCloseRef.current = false;
    setIsCopied(false);
    setRelinkSuccess(false);
    setAutosaveStatus('idle');
    setIsTocOpen(false);
  }, [previewContent]);

  useEffect(() => {
    return () => { if (relinkTimerRef.current) window.clearTimeout(relinkTimerRef.current); };
  }, []);

  useEffect(() => {
    const autosaveGenRefAtCleanup = autosaveGenRef;
    return () => {
      if (!isDirtyRef.current || saveErrorOnCloseRef.current) return;
      if (autosaveTimerRef.current) window.clearTimeout(autosaveTimerRef.current);
      const path = htmlPathRef.current;
      const snap = getHtmlRef.current?.() ?? '';
      if (path && snap && snap !== lastPersistedRef.current) {
        void window.pywebview?.api?.save_html_content(path, snap, ++autosaveGenRefAtCleanup.current);
      }
    };
  }, []); // empty deps: runs cleanup only on unmount

  useEffect(() => {
    (window as unknown as Record<string, unknown>).__elSbobinatorGetDirtyEditorContent = () => {
      if (!isDirtyRef.current) return null;
      const path = htmlPathRef.current;
      if (!path) return null;
      const snap = getHtmlRef.current?.() ?? '';
      if (snap === lastPersistedRef.current) return null;
      return { path, content: snap };
    };
    return () => {
      delete (window as unknown as Record<string, unknown>).__elSbobinatorGetDirtyEditorContent;
    };
  }, []); // empty deps: register once on mount, remove on unmount

  const flushAndClose = useCallback(async () => {
    if (isDirtyRef.current && !saveErrorOnCloseRef.current) {
      if (autosaveTimerRef.current) { window.clearTimeout(autosaveTimerRef.current); autosaveTimerRef.current = null; }
      const path = htmlPathRef.current;
      const snap = getHtmlRef.current?.() ?? '';
      if (path && snap && snap !== lastPersistedRef.current && window.pywebview?.api?.save_html_content) {
        setAutosaveStatus('saving');
        try {
          const res = await window.pywebview.api.save_html_content(path, snap, ++autosaveGenRef.current);
          if (res.ok) { lastPersistedRef.current = snap; isDirtyRef.current = false; }
          else { saveErrorOnCloseRef.current = true; setAutosaveStatus('error'); return; }
        } catch { saveErrorOnCloseRef.current = true; setAutosaveStatus('error'); return; }
      }
    }
    onClose();
  }, [onClose]);

  useEffect(() => {
    if (previewContent === null) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') void flushAndClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [flushAndClose, previewContent]);

  const scheduleAutosave = useCallback(() => {
    if (!htmlPath || previewContent === null) return;
    isDirtyRef.current = true;
    saveErrorOnCloseRef.current = false;
    if (autosaveTimerRef.current) window.clearTimeout(autosaveTimerRef.current);
    const savedForPath = htmlPath;
    const gen = ++autosaveGenRef.current;
    autosaveTimerRef.current = window.setTimeout(async () => {
      if (!isDirtyRef.current || !window.pywebview?.api?.save_html_content) return;
      const snap = getHtmlRef.current?.() ?? '';
      if (snap === lastPersistedRef.current) { isDirtyRef.current = false; return; }
      setAutosaveStatus('saving');
      try {
        const res = await window.pywebview.api.save_html_content(savedForPath, snap, gen);
        if (htmlPathRef.current !== savedForPath) return;
        if (gen !== autosaveGenRef.current) return;
        if (res.ok) { lastPersistedRef.current = snap; isDirtyRef.current = false; setAutosaveStatus('saved'); }
        else setAutosaveStatus('error');
      } catch { setAutosaveStatus('error'); }
    }, 700);
  }, [htmlPath, previewContent]);

  useEffect(() => {
    if (autosaveStatus !== 'saved') return;
    let cancelled = false;
    const id = window.setTimeout(() => { if (!cancelled) setAutosaveStatus('idle'); }, 1500);
    return () => { cancelled = true; window.clearTimeout(id); };
  }, [autosaveStatus]);

  const handleCopy = async () => {
    const normalizedHtml = normalizePreviewHtmlContent(getHtmlRef.current?.() ?? lastPersistedRef.current);
    const temp = document.createElement('div');
    temp.innerHTML = normalizedHtml;
    try {
      const htmlBlob = new Blob([normalizedHtml], { type: 'text/html' });
      const textBlob = new Blob([temp.textContent || temp.innerText || ''], { type: 'text/plain' });
      await navigator.clipboard.write([new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob })]);
    } catch (_) { navigator.clipboard.writeText(temp.textContent || temp.innerText || ''); }
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  const scrollToHeading = (heading: Heading) => {
    const { text, level, id } = heading;
    const idx = headings.findIndex(h => h.id === id);
    if (idx === -1) return;
    const occurrencesBefore = headings
      .slice(0, idx)
      .filter(h => h.level === level && h.text.trim() === text.trim())
      .length;
    const els = Array.from(document.querySelectorAll(`.tiptap-editor h${level}`))
      .filter(el => el.textContent?.trim() === text.trim());
    els[occurrencesBefore]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <AnimatePresence>
      {previewContent !== null && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => void flushAndClose()}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
          style={{ background: 'var(--bg-overlay)', backdropFilter: 'blur(10px)' }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            onClick={event => event.stopPropagation()}
            className="modal-card w-full max-h-[88vh] flex flex-col overflow-hidden"
            style={{ maxWidth: isTocOpen ? '1400px' : '1100px', transition: 'max-width 0.25s ease' }}
          >
            <div className="px-4 py-4 sm:px-5 flex items-center justify-between gap-3 border-b shrink-0" style={{ borderColor: 'var(--border-subtle)' }}>
              <h3 className="font-semibold text-lg flex items-center gap-2 truncate min-w-0" style={{ color: 'var(--text-primary)' }}>
                <FileText className="w-5 h-5 shrink-0" style={{ color: 'var(--text-muted)' }} />
                <span className="truncate">Anteprima: {previewTitle}</span>
              </h3>
              <div className="flex gap-2 shrink-0 flex-wrap justify-end">
                <span
                  className="inline-flex h-[38px] items-center rounded-[14px] px-3 text-sm font-medium"
                  style={{
                    color: autosaveStatus === 'error' ? 'var(--error-text)' : autosaveStatus === 'saved' ? 'var(--success-text)' : 'var(--text-muted)',
                    background: 'rgba(255,255,255,0.02)',
                    border: '1px solid var(--border-default)',
                  }}
                >
                  {autosaveStatus === 'saving' ? 'Salvataggio...' : autosaveStatus === 'saved' ? 'Salvato' : autosaveStatus === 'error' ? 'Errore salvataggio' : 'Salvataggio automatico'}
                </span>
                {htmlPath && (
                  <button
                    onClick={() => window.pywebview?.api?.open_file?.(htmlPath)}
                    className="icon-button modal-icon-button"
                    style={{ color: 'var(--text-muted)' }}
                    title="Apri file HTML"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </button>
                )}
                <div className="relative">
                  <button
                    onClick={handleCopy}
                    className="icon-button modal-icon-button"
                    style={isCopied ? { borderColor: 'var(--success-ring)', color: 'var(--success-text)' } : { color: 'var(--text-muted)' }}
                    title={isCopied ? 'Copiato!' : 'Copia per Google Docs'}
                  >
                    {isCopied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  </button>
                </div>
                <button onClick={() => void flushAndClose()} className="icon-button modal-icon-button" style={{ color: 'var(--text-muted)' }} title={autosaveStatus === 'error' ? 'Chiudi senza salvare' : undefined}>
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="flex-1 min-h-0 overflow-hidden flex flex-row">
              {/* Editor area + Player column */}
              <div className="flex-1 min-h-0 flex flex-col">
                <div className="flex-1 min-h-0 flex flex-col">
                  <Suspense fallback={<div className="p-6 text-sm" style={{ color: 'var(--text-muted)' }}>Caricamento editor...</div>}>
                    <LazyRichTextEditor
                      initialContent={previewContent || ''}
                      onChange={scheduleAutosave}
                      onEditorReady={getHtml => { getHtmlRef.current = getHtml; }}
                      initialScrollTop={previewInitScrollTop}
                      onScrollTopChange={onScrollTopChange}
                      onHeadingsChange={setHeadings}
                      isTocOpen={isTocOpen}
                      onTocToggle={() => setIsTocOpen(p => !p)}
                      tocHeadings={headings}
                      onScrollToHeading={scrollToHeading}
                    />
                  </Suspense>
                </div>

                {(audioSrc || audioRelinkNeeded) && (
                  <div className="shrink-0 border-t px-4 sm:px-5" style={{ borderColor: 'var(--border-subtle)' }}>
                    {audioSrc ? (
                      <Suspense fallback={<div className="p-4 text-sm" style={{ color: 'var(--text-muted)' }}>Caricamento player...</div>}>
                        <LazyAudioPlayer
                          src={audioSrc}
                          initialTime={previewInitAudio.time}
                          initialPlaybackRate={previewInitAudio.playbackRate}
                          initialVolume={previewInitAudio.volume}
                          onStateChange={onAudioStateChange}
                        />
                      </Suspense>
                    ) : (
                      <div className="flex items-center justify-between gap-3 py-3.5">
                        <div className="min-w-0">
                          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Audio non trovato</p>
                          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                            Il file originale è stato spostato. Selezionalo di nuovo per riattivare il player.
                          </p>
                        </div>
                        <button
                          onClick={async () => {
                            if (isRelinking) return;
                            setIsRelinking(true);
                            try {
                              const ok = await onRelink();
                              if (ok) {
                                if (relinkTimerRef.current) window.clearTimeout(relinkTimerRef.current);
                                setRelinkSuccess(true);
                                relinkTimerRef.current = window.setTimeout(() => setRelinkSuccess(false), 3000);
                              }
                            } finally {
                              setIsRelinking(false);
                            }
                          }}
                          disabled={isRelinking}
                          className="modal-action-button shrink-0"
                          style={relinkSuccess ? { borderColor: 'var(--success-ring)', color: 'var(--success-text)' } : {}}
                        >
                          {relinkSuccess ? <><Check className="w-3.5 h-3.5" /> Ricollegato</> : isRelinking ? 'Selezione...' : 'Ricollega audio'}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>

            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
