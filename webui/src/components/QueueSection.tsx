import { useMemo, type Dispatch, type SetStateAction } from 'react';
import { DndContext, closestCenter, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { motion, AnimatePresence } from 'motion/react';
import { FileAudio, ListOrdered, Play, Square } from 'lucide-react';
import type { AppStatus, FileItem } from '../appState';
import { shortModelName } from '../utils';
import { QueueFileCard } from './QueueFileCard';

interface QueueSectionProps {
  pendingFiles: FileItem[];
  appState: AppStatus;
  autoContinue: boolean;
  setAutoContinue: Dispatch<SetStateAction<boolean>>;
  preferredModel: string;
  queuedCount: number;
  canStart: boolean;
  hasApiKey: boolean;
  isApiKeyValid: boolean;
  currentPhase: string;
  dndSensors: ReturnType<typeof useSensors>;
  onDragEnd: (event: DragEndEvent) => void;
  onRemove: (id: string) => void;
  onRetry: (id: string) => void;
  onPreview: (htmlPath: string, filename: string, sourcePath?: string, fileId?: string, sessionDir?: string) => void;
  onOpenFile: (path: string) => void;
  onStart: () => void;
  onStop: () => void;
}

export function QueueSection({
  pendingFiles, appState, autoContinue, setAutoContinue, preferredModel,
  queuedCount, canStart, hasApiKey, isApiKeyValid, currentPhase,
  dndSensors, onDragEnd, onRemove, onRetry, onPreview, onOpenFile,
  onStart, onStop,
}: QueueSectionProps) {
  const sortableIds = useMemo(() => pendingFiles.map(f => f.id), [pendingFiles]);

  return (
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

          <DndContext sensors={dndSensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
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
                      onRemove={onRemove}
                      onRetry={(id) => onRetry(id)}
                      onPreview={onPreview}
                      onOpenFile={onOpenFile}
                    />
                  );
                })}
              </AnimatePresence>
            </SortableContext>
          </DndContext>

          {(appState !== 'idle' || queuedCount > 0) && (
            <div className="pt-4 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
              <AnimatePresence mode="wait">
                {appState === 'idle' && (
                  <motion.div key="idle" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                    <button onClick={onStart} disabled={!canStart}
                      className={`premium-button w-full text-lg${canStart ? ' premium-button--ready' : ''}`}
                      style={canStart ? {} : { cursor: 'not-allowed' }}>
                      <Play className="w-5 h-5 fill-current" />
                      {!hasApiKey ? '⚠️ Inserisci API Key nelle impostazioni' : !isApiKeyValid ? '⚠️ API Key non valida' : `Avvia sbobinatura (${queuedCount} file)`}
                    </button>
                  </motion.div>
                )}
                {appState === 'processing' && (
                  <motion.div key="processing" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="flex justify-end">
                    <button onClick={onStop} className="premium-button-secondary compact-button px-5 py-2" style={{ color: 'var(--error-text)', borderColor: 'var(--error-ring)', background: 'var(--bg-elevated)' }}>
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
  );
}
