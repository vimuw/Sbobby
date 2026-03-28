import React, { Suspense, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Check, Copy, FileText, Menu, X } from 'lucide-react';
import type { Heading } from '../../RichTextEditor';

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
  const [isTocOpen, setIsTocOpen] = useState(false);
  const [headings, setHeadings] = useState<Heading[]>([]);

  const scrollToHeading = (text: string, level: number) => {
    const els = document.querySelectorAll(`.tiptap-editor h${level}`);
    for (const el of Array.from(els)) {
      if (el.textContent?.trim() === text.trim()) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        break;
      }
    }
  };

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
                <button onClick={onClose} className="icon-button h-11 w-11 rounded-[14px]" style={{ color: 'var(--text-muted)' }}>
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="flex-1 min-h-0 overflow-hidden flex flex-row">
              {/* Left TOC Sidebar */}
              <div className="toc-left-sidebar" style={{ width: isTocOpen ? 260 : 44, opacity: 1 }}>
                {!isTocOpen && (
                  <button
                    className="toc-left-btn"
                    onClick={() => setIsTocOpen(true)}
                    title="Apri indice"
                  >
                    <Menu className="w-4 h-4" />
                  </button>
                )}
                {isTocOpen && (
                  <>
                    <div className="toc-left-header">
                      <span>Indice</span>
                      <button className="toc-left-close" onClick={() => setIsTocOpen(false)} title="Chiudi">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <nav className="toc-left-nav">
                      {headings.length === 0 ? (
                        <p className="toc-empty">Nessun titolo</p>
                      ) : (
                        headings.map(h => (
                          <button
                            key={h.id}
                            className={`toc-item toc-item-h${h.level}`}
                            style={{ paddingLeft: `${(h.level - 1) * 12 + 14}px` }}
                            onClick={() => scrollToHeading(h.text, h.level)}
                            title={h.text}
                          >
                            {h.text}
                          </button>
                        ))
                      )}
                    </nav>
                  </>
                )}
              </div>

              {/* Editor area + Player column */}
              <div className="flex-1 min-h-0 flex flex-col">
                <div className="flex-1 min-h-0 overflow-y-auto">
                  <Suspense fallback={<div className="p-6 text-sm" style={{ color: 'var(--text-muted)' }}>Caricamento editor...</div>}>
                    <LazyRichTextEditor
                      initialContent={previewContent || ''}
                      onChange={onChange}
                      initialScrollTop={previewInitScrollTop}
                      onScrollTopChange={onScrollTopChange}
                      onHeadingsChange={setHeadings}
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
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
