import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { CheckCircle, Search } from 'lucide-react';
import type { AppStatus, FileItem } from '../appState';
import { CompletedFileCard } from './QueueFileCard';

interface CompletedSectionProps {
  doneFiles: FileItem[];
  appState: AppStatus;
  onRemove: (id: string) => void;
  onPreview: (htmlPath: string, filename: string, sourcePath?: string, fileId?: string, sessionDir?: string) => void;
  onOpenFile: (path: string) => void;
  onClearAll: () => void;
}

export function CompletedSection({ doneFiles, appState, onRemove, onPreview, onOpenFile, onClearAll }: CompletedSectionProps) {
  const [completedSearch, setCompletedSearch] = useState('');

  const filteredDoneFiles = completedSearch.trim()
    ? doneFiles.filter(f => f.name.toLowerCase().includes(completedSearch.toLowerCase()))
    : doneFiles;

  return (
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
                  onClick={onClearAll}
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
                onRemove={onRemove}
                onPreview={onPreview}
                onOpenFile={onOpenFile}
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
  );
}
