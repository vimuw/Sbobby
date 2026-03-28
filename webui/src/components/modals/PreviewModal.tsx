import React, { Suspense, useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { BookOpen, Check, Copy, FileText, X } from 'lucide-react';

const LazyAudioPlayer = React.lazy(() => import('../../AudioPlayer').then(module => ({ default: module.AudioPlayer })));
const LazyRichTextEditor = React.lazy(() => import('../../RichTextEditor').then(module => ({ default: module.RichTextEditor })));

interface PreviewModalProps {
  previewContent: string | null;
  previewTitle: string;
  editedContent: string;
  onChange: (content: string) => void;
  onClose: () => void;
  audioSrc: string | null;
  audioRelinkNeeded: boolean;
  onRelink: () => void;
  autosaveStatus: 'idle' | 'saving' | 'saved' | 'error';
  isCopied: boolean;
  onCopy: () => void;
  previewInitAudio: { time?: number; playbackRate?: number; volume?: number };
  previewInitScrollTop: number | undefined;
  onAudioStateChange: (state: { currentTime: number; playbackRate: number; volume: number }) => void;
  onScrollTopChange: (scrollTop: number) => void;
}

export function PreviewModal({
  previewContent, previewTitle, editedContent, onChange, onClose,
  audioSrc, audioRelinkNeeded, onRelink,
  autosaveStatus, isCopied, onCopy,
  previewInitAudio, previewInitScrollTop,
  onAudioStateChange, onScrollTopChange,
}: PreviewModalProps) {
  const [headings, setHeadings] = useState<{ id: string; level: number; text: string }[]>([]);
  const [isTocOpen, setIsTocOpen] = useState(false);
  const scrollToHeadingRef = useRef<((index: number) => void) | null>(null);

  const handleHeadingsChange = useCallback((
    newHeadings: { id: string; level: number; text: string }[],
    scrollTo: (index: number) => void
  ) => {
    setHeadings(newHeadings);
    scrollToHeadingRef.current = scrollTo;
  }, []);

  return (
    <AnimatePresence>
      {previewContent !== null && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
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
                <span
                  className="inline-flex h-11 items-center rounded-[14px] px-3 text-sm font-medium"
                  style={{
                    color: autosaveStatus === 'error' ? 'var(--error-text)' : autosaveStatus === 'saved' ? 'var(--success-text)' : 'var(--text-muted)',
                    background: 'rgba(255,255,255,0.02)',
                    border: '1px solid var(--border-default)',
                  }}
                >
                  {autosaveStatus === 'saving' ? 'Salvataggio...' : autosaveStatus === 'saved' ? 'Salvato' : autosaveStatus === 'error' ? 'Errore salvataggio' : 'Salvataggio automatico'}
                </span>
                <div className="relative">
                  <button
                    onClick={onCopy}
                    className="icon-button h-9 w-9 rounded-[12px]"
                    style={isCopied ? { borderColor: 'var(--success-ring)', color: 'var(--success-text)' } : { color: 'var(--text-muted)' }}
                    title={isCopied ? 'Copiato!' : 'Copia per Google Docs'}
                  >
                    {isCopied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  </button>
                </div>
                <button
                  onClick={() => setIsTocOpen(v => !v)}
                  className="icon-button h-11 w-11 rounded-[14px]"
                  style={isTocOpen ? { borderColor: 'var(--accent-ring)', color: 'var(--accent-text)' } : { color: 'var(--text-muted)' }}
                  title={isTocOpen ? 'Nascondi indice' : 'Mostra indice capitoli'}
                >
                  <BookOpen className="w-5 h-5" />
                </button>
                <button onClick={onClose} className="icon-button h-11 w-11 rounded-[14px]" style={{ color: 'var(--text-muted)' }}>
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="flex flex-1 min-h-0 overflow-hidden">
              {isTocOpen && headings.length > 0 && (
                <aside
                  className="w-56 shrink-0 overflow-y-auto border-r p-2 hidden sm:block"
                  style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-surface)' }}
                >
                  {headings.map((h, i) => (
                    <button
                      key={h.id}
                      className="block w-full text-left text-xs py-1 rounded hover:bg-white/5 truncate"
                      style={{ paddingLeft: `${(h.level - 1) * 12 + 8}px`, color: 'var(--text-muted)' }}
                      onClick={() => scrollToHeadingRef.current?.(i)}
                    >
                      {h.text}
                    </button>
                  ))}
                </aside>
              )}
              <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
                <Suspense fallback={<div className="p-6 text-sm" style={{ color: 'var(--text-muted)' }}>Caricamento editor...</div>}>
                  <LazyRichTextEditor
                    initialContent={previewContent || ''}
                    onChange={onChange}
                    initialScrollTop={previewInitScrollTop}
                    onScrollTopChange={onScrollTopChange}
                    onHeadingsChange={handleHeadingsChange}
                  />
                </Suspense>
              </div>
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
                        Il file originale e stato spostato. Selezionalo di nuovo per riattivare il player.
                      </p>
                    </div>
                    <button onClick={onRelink} className="premium-button-secondary compact-button shrink-0">
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
  );
}
