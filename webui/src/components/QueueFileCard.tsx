import React from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { AlertCircle, CheckCircle, Clock, ExternalLink, Eye, FileAudio, FolderOpen, GripVertical, Trash2, XCircle } from 'lucide-react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { AppStatus, FileItem } from '../appState';
import { formatDuration, formatSize } from '../utils';

interface QueueFileCardProps {
  file: FileItem;
  appState: AppStatus;
  currentPhase?: string;
  workDone: { chunks: number; macro: number; boundary: number };
  workTotals: { chunks: number; macro: number; boundary: number };
  etaLabel: string | null;
  activeProgress?: number;
  onRemove: (id: string) => void;
  onPreview: (htmlPath: string, filename: string, sourcePath?: string, fileId?: string) => void;
  onOpenFile: (path: string) => void;
  onOpenDir: (path: string) => void;
}

function getProcessingDetails(phaseText?: string) {
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
}

function QueueFileCardInner({
  file, appState, currentPhase, workDone, workTotals, etaLabel, activeProgress,
  onRemove, onPreview, onOpenFile, onOpenDir,
}: QueueFileCardProps) {
  const processingDetails = file.status === 'processing' ? getProcessingDetails(currentPhase) : null;
  const isCanceling = appState === 'canceling' && file.status === 'processing';
  const isDraggable = file.status === 'queued' && appState === 'idle';

  const { attributes, listeners, setNodeRef, transform, transition: dndTransition, isDragging } = useSortable({
    id: file.id,
    disabled: !isDraggable,
  });

  const sortableStyle: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition: dndTransition ?? undefined,
    zIndex: isDragging ? 50 : undefined,
    position: 'relative',
  };

  return (
    <div ref={setNodeRef} style={sortableStyle} {...attributes}>
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: isDragging ? 0.4 : 1, y: 0 }}
        exit={{ opacity: 0, transition: { duration: 0.11, ease: 'easeIn' } }}
        transition={{
          opacity: { duration: 0.2, ease: 'easeOut' },
          y: { type: 'spring', stiffness: 380, damping: 30, mass: 0.8 },
        }}
        className={`queue-card relative transition-colors ${file.status === 'processing' ? (isCanceling ? 'canceling-card px-5 py-4' : 'processing-card px-5 py-4') : 'p-5'}`}
        style={{
          border: `1px solid ${
            file.status === 'processing'
              ? isCanceling ? 'var(--warning-ring)' : 'var(--processing-ring)'
              : file.status === 'done'
                ? 'var(--success-ring)'
                : file.status === 'error'
                  ? 'var(--error-ring)'
                  : 'var(--card-queued-border)'
          }`,
          background: file.status === 'processing'
            ? isCanceling
              ? 'linear-gradient(180deg, rgba(255,255,255,0.02), var(--warning-subtle))'
              : 'linear-gradient(180deg, rgba(255,255,255,0.02), var(--processing-bg))'
            : file.status === 'error'
              ? 'var(--error-subtle)'
              : 'rgba(255,255,255,0.03)',
        }}
      >
        <div className="relative z-10 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 overflow-hidden flex-1">
            {isDraggable && (
              <button
                {...listeners}
                className="drag-handle-btn shrink-0"
                tabIndex={-1}
                aria-label="Trascina per riordinare"
              >
                <GripVertical className="w-4 h-4" />
              </button>
            )}
            <div
              className="shrink-0 flex items-center justify-center w-10 h-10 rounded-xl"
              style={{
                background: file.status === 'processing'
                  ? isCanceling ? 'var(--warning-subtle)' : 'var(--processing-bg)'
                  : file.status === 'error'
                    ? 'var(--error-subtle)'
                    : 'rgba(255,255,255,0.03)',
                color: file.status === 'done'
                  ? 'var(--success-text)'
                  : file.status === 'processing'
                    ? isCanceling ? 'var(--warning-text)' : 'var(--processing-text)'
                    : file.status === 'error'
                      ? 'var(--error-text)'
                      : 'var(--text-muted)',
              }}
            >
              {file.status === 'done'
                ? <CheckCircle className="w-5 h-5" />
                : file.status === 'processing'
                  ? isCanceling
                    ? <XCircle className="w-5 h-5" />
                    : <Clock className="w-5 h-5 animate-pulse" />
                  : file.status === 'error'
                    ? <AlertCircle className="w-5 h-5" />
                    : <FileAudio className="w-5 h-5" />}
            </div>
            <div className="min-w-0 flex-1">
              <h4 className="text-base font-semibold truncate tracking-tight" style={{ color: 'var(--text-primary)' }}>{file.name}</h4>
              <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
                <span>{formatSize(file.size)}</span>
                {file.duration > 0 && (
                  <>
                    <span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} />
                    <span>{formatDuration(file.duration)}</span>
                  </>
                )}
                {file.status === 'done' && (
                  <>
                    <span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} />
                    <span style={{ color: 'var(--success-text)' }}>Completato</span>
                  </>
                )}
                {file.status === 'error' && (
                  <>
                    <span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} />
                    <span style={{ color: 'var(--error-text)' }}>{file.errorText || 'Errore'}</span>
                  </>
                )}
              </div>
              {file.status === 'processing' && processingDetails && (
                <motion.div
                  layout="position"
                  className="mt-2 flex min-h-7 flex-wrap items-center gap-1.5"
                  transition={{ layout: { duration: 0.2, ease: [0.22, 1, 0.36, 1] } }}
                >
                  <span className={`helper-chip processing-chip-compact ${isCanceling ? 'canceling-chip' : 'processing-chip'}`}>
                    <span className="inline-flex h-2 w-2 rounded-full animate-pulse" style={{ background: isCanceling ? 'var(--warning-text)' : 'var(--processing-dot)' }} />
                    {isCanceling ? 'Annullamento in corso...' : 'In elaborazione'}
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
                <button
                  onClick={(e) => { e.stopPropagation(); onPreview(file.outputHtml!, file.name, file.path, file.id); }}
                  className="icon-button compact-icon-button"
                  style={{ color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.03)', borderColor: 'var(--border-default)' }}
                  title="Anteprima testo"
                >
                  <Eye className="w-4 h-4" />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onOpenFile(file.outputHtml!); }}
                  className="icon-button compact-icon-button"
                  style={{ color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.03)', borderColor: 'var(--border-default)' }}
                  title="Apri nel browser"
                >
                  <ExternalLink className="w-4 h-4" />
                </button>
                {file.outputDir && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onOpenDir(file.outputDir!); }}
                    className="icon-button compact-icon-button"
                    style={{ color: 'var(--text-muted)' }}
                    title="Apri cartella"
                  >
                    <FolderOpen className="w-4 h-4" />
                  </button>
                )}
              </>
            )}
            {appState !== 'processing' && (
              <button
                onClick={() => onRemove(file.id)}
                className="icon-button compact-icon-button"
                style={{ color: 'var(--error-text)', borderColor: 'var(--error-ring)', background: 'var(--error-subtle)' }}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {file.status === 'processing' && (
          <div className="relative z-10 mt-3">
            <div
              className="flex items-center justify-between gap-3 mb-1.5 text-[10px] font-medium uppercase tracking-[0.14em]"
              style={{ color: 'var(--text-muted)' }}
            >
              <span>{isCanceling ? 'In attesa di interruzione' : (processingDetails?.title ?? 'Generazione sbobina')}</span>
              <span style={{ color: 'var(--text-primary)' }}>{activeProgress ?? file.progress}%</span>
            </div>
            <div className="processing-progress h-2 w-full rounded-full overflow-hidden" style={{ background: 'var(--progress-bg)' }}>
              <motion.div
                className="processing-progress-fill h-full rounded-full"
                style={{ background: isCanceling ? 'linear-gradient(90deg, var(--warning-bg), var(--warning-text))' : 'linear-gradient(90deg, var(--accent-gradient-start), var(--accent-gradient-end))' }}
                initial={{ width: 0 }}
                animate={{ width: `${activeProgress ?? file.progress}%` }}
                transition={{ ease: 'linear', duration: 0.3 }}
              />
            </div>
            <div className="flex justify-between mt-1.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>
              <span>
                {processingDetails?.chunk
                  ? processingDetails.chunk
                  : workTotals.chunks > 0
                    ? `Chunk ${workDone.chunks}/${workTotals.chunks}`
                    : 'Avanzamento attivo'}
              </span>
              {etaLabel && <span style={{ color: 'var(--text-secondary)' }}>ETA {etaLabel}</span>}
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
}

export const QueueFileCard = React.memo(QueueFileCardInner);
