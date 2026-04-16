import React from 'react';
import { motion } from 'motion/react';
import { AlertCircle, CheckCircle, Clock, ExternalLink, FileAudio, FolderOpen, GripVertical, PenLine, RotateCcw, Trash2, XCircle } from 'lucide-react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { AppStatus, FileItem } from '../appState';
import { errorLabel, formatDuration, formatRelativeTime, formatSize, shortModelName } from '../utils';

interface QueueFileCardProps {
  file: FileItem;
  appState: AppStatus;
  currentPhase?: string;
  onRemove: (id: string) => void;
  onRetry: (id: string) => void;
  onPreview: (htmlPath: string, filename: string, sourcePath?: string, fileId?: string) => void;
  onOpenFile: (path: string) => void;
  /** @deprecated kept for interface compatibility */
}

function abbreviatePath(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  if (parts.length <= 2) return path;
  return `…/${parts.slice(-2).join('/')}`;
}

function QueueFileCardInner({
  file, appState, currentPhase: _currentPhase,
  onRemove,
  onRetry,
  onPreview: _onPreview,
  onOpenFile: _onOpenFile,
}: QueueFileCardProps) {
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
        className={`queue-card relative transition-colors ${file.status === 'processing' ? (isCanceling ? 'canceling-card px-5 py-4' : 'processing-card px-5 py-4') : file.status === 'queued' ? 'p-4' : 'p-5'}`}
        style={{
          border: `1px solid ${
            file.status === 'processing'
              ? isCanceling ? 'var(--error-ring)' : 'var(--processing-ring)'
              : file.status === 'error'
                ? 'var(--error-ring)'
                : 'var(--card-queued-border)'
          }`,
          background: file.status === 'processing'
            ? isCanceling
              ? 'linear-gradient(180deg, rgba(255,255,255,0.02), var(--error-subtle))'
              : 'linear-gradient(180deg, rgba(255,255,255,0.02), var(--processing-bg))'
            : file.status === 'error'
              ? 'var(--error-subtle)'
              : 'rgba(255,255,255,0.03)',
        }}
      >
        <div className="relative z-10 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 overflow-hidden flex-1">
            {isDraggable && (
              <div className="group/drag flex items-center shrink-0 gap-1">
                <button
                  {...listeners}
                  className="drag-handle-btn"
                  tabIndex={-1}
                  aria-label="Trascina per riordinare"
                >
                  <GripVertical className="w-4 h-4" />
                </button>
                <span
                  className="text-[10px] select-none opacity-0 group-hover/drag:opacity-50 transition-opacity duration-150 whitespace-nowrap"
                  style={{ color: 'var(--text-faint)' }}
                >
                  trascina
                </span>
              </div>
            )}
            <div
              className="shrink-0 flex items-center justify-center w-10 h-10 rounded-xl"
              style={{
                background: file.status === 'processing'
                  ? isCanceling ? 'var(--error-subtle)' : 'var(--processing-bg)'
                  : file.status === 'error'
                    ? 'var(--error-subtle)'
                    : 'rgba(255,255,255,0.03)',
                color: file.status === 'processing'
                  ? isCanceling ? 'var(--error-text)' : 'var(--processing-text)'
                  : file.status === 'error'
                    ? 'var(--error-text)'
                    : 'var(--text-muted)',
              }}
            >
              {file.status === 'processing'
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
                {file.status === 'error' && (
                  <>
                    <span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} />
                    <span title={file.errorText} style={{ color: 'var(--error-text)' }}>{errorLabel(file.errorText)}</span>
                  </>
                )}
              </div>
              {file.status === 'processing' && (
                <motion.div
                  layout="position"
                  className="mt-2 flex min-h-7 flex-wrap items-center gap-1.5"
                  transition={{ layout: { duration: 0.2, ease: [0.22, 1, 0.36, 1] } }}
                >
                  <span className={`helper-chip processing-chip-compact ${isCanceling ? 'canceling-chip' : 'processing-chip'}`}>
                    <span className="inline-flex h-2 w-2 rounded-full animate-pulse" style={{ background: isCanceling ? 'var(--error-text)' : 'var(--processing-dot)' }} />
                    {isCanceling ? 'Annullamento in corso' : 'In elaborazione'}
                  </span>
                </motion.div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {appState === 'idle' && file.status === 'error' && (
              <button
                onClick={() => onRetry(file.id)}
                className="icon-button compact-icon-button"
                style={{ color: 'var(--error-text)', borderColor: 'var(--error-ring)', background: 'var(--error-subtle)' }}
                title="Riprova"
                aria-label="Riprova"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
            )}
            {appState === 'idle' && (
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

      </motion.div>
    </div>
  );
}

export const QueueFileCard = React.memo(QueueFileCardInner);

interface CompletedFileCardProps {
  file: FileItem;
  isNewest: boolean;
  onRemove: (id: string) => void;
  onPreview: (htmlPath: string, filename: string, sourcePath?: string, fileId?: string) => void;
  onOpenFile: (path: string) => void;
}

function CompletedFileCardInner({ file, isNewest, onRemove, onPreview, onOpenFile }: CompletedFileCardProps) {
  const isClickable = Boolean(file.outputHtml);
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, transition: { duration: 0.11, ease: 'easeIn' } }}
      transition={{
        opacity: { duration: 0.2, ease: 'easeOut' },
        y: { type: 'spring', stiffness: 380, damping: 30, mass: 0.8 },
      }}
      onClick={isClickable ? () => onPreview(file.outputHtml!, file.name, file.path, file.id) : undefined}
      className={`queue-card relative p-5 transition-colors group/card ${isClickable ? 'cursor-pointer' : ''}`}
      style={{
        border: '1px solid var(--success-ring)',
        background: isNewest ? 'rgba(22,163,74,0.04)' : 'rgba(255,255,255,0.03)',
        boxShadow: isNewest ? '0 0 0 2px rgba(22,163,74,0.10)' : undefined,
      }}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 overflow-hidden flex-1">
          <div
            className="shrink-0 flex items-center justify-center w-10 h-10 rounded-xl"
            style={{ background: 'rgba(255,255,255,0.03)', color: 'var(--success-text)' }}
          >
            <CheckCircle className="w-5 h-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 min-w-0">
              <h4 className="text-base font-semibold truncate tracking-tight" style={{ color: 'var(--text-primary)' }}>{file.name}</h4>
              {isNewest && (
                <span className="shrink-0 whitespace-nowrap text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full" style={{ background: 'var(--success-subtle)', color: 'var(--success-text)', border: '1px solid var(--success-ring)' }}>
                  Nuovo
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
              <span>{formatSize(file.size)}</span>
              {file.duration > 0 && (
                <>
                  <span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} />
                  <span>{formatDuration(file.duration)}</span>
                </>
              )}
              {(file.primaryModel || file.effectiveModel) && (
                <>
                  <span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} />
                  <span title={file.primaryModel || file.effectiveModel}>
                    {shortModelName(file.primaryModel || file.effectiveModel!)}
                  </span>
                  {file.primaryModel && file.effectiveModel && file.primaryModel !== file.effectiveModel && (
                    <span
                      className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full"
                      style={{ background: 'var(--warning-subtle)', color: 'var(--warning-text)', border: '1px solid var(--warning-ring)' }}
                      title={`Fallback usato: ${shortModelName(file.effectiveModel)}`}
                    >
                      fallback
                    </span>
                  )}
                </>
              )}
              <span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} />
              <span style={{ color: 'var(--success-text)' }}>
                {file.completedAt ? formatRelativeTime(file.completedAt) : 'Completato'}
              </span>
            </div>
            {file.outputHtml && (
              <div
                className="mt-1 flex items-center gap-1 text-[11px] hover:underline"
                style={{ color: 'var(--text-faint)', cursor: 'pointer' }}
                onClick={(e) => { e.stopPropagation(); onOpenFile(file.outputDir ?? file.outputHtml!); }}
                title={`Apri cartella: ${file.outputDir ?? file.outputHtml}`}
              >
                <FolderOpen className="w-3 h-3 shrink-0" />
                <span className="truncate">{abbreviatePath(file.outputHtml)}</span>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {file.outputHtml && (
            <button
              onClick={(e) => { e.stopPropagation(); onPreview(file.outputHtml!, file.name, file.path, file.id); }}
              className="icon-button"
              style={{ color: 'var(--success-text)', borderColor: 'var(--success-ring)', background: 'var(--success-subtle)', paddingInline: '10px', gap: '5px', height: '34px', borderRadius: '10px', width: 'auto' }}
              title="Apri editor"
              aria-label="Apri editor"
            >
              <PenLine className="w-3.5 h-3.5 shrink-0" />
              <span className="text-xs font-medium">Modifica</span>
            </button>
          )}
          {file.outputHtml && (
            <button
              onClick={(e) => { e.stopPropagation(); onOpenFile(file.outputHtml!); }}
              className="icon-button compact-icon-button"
              style={{ color: 'var(--text-muted)' }}
              title="Apri nel browser"
              aria-label="Apri nel browser"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          )}
          <button
              onClick={(e) => { e.stopPropagation(); onRemove(file.id); }}
              className="icon-button compact-icon-button"
              style={{ color: 'var(--error-text)', borderColor: 'var(--error-ring)', background: 'var(--error-subtle)' }}
              title="Rimuovi"
              aria-label="Rimuovi"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
        </div>
      </div>
    </motion.div>
  );
}

export const CompletedFileCard = React.memo(CompletedFileCardInner);
