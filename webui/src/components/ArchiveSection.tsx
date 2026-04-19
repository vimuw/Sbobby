import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, ExternalLink, FolderOpen, History, Search, Trash2 } from 'lucide-react';
import type { ArchiveSession } from '../bridge';
import { formatRelativeTime, shortModelName } from '../utils';

const ARCHIVE_PAGE_SIZE = 5;

interface ArchiveSectionProps {
  sessions: ArchiveSession[];
  onPreview: (htmlPath: string, filename: string, sourcePath?: string, fileId?: string, sessionDir?: string) => void;
  onOpenFile: (path: string) => void;
  onDeleteSession: (sessionDir: string, name: string) => void;
}

export function ArchiveSection({ sessions, onPreview, onOpenFile, onDeleteSession }: ArchiveSectionProps) {
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const [archiveSearch, setArchiveSearch] = useState('');
  const [archiveSort, setArchiveSort] = useState<'newest' | 'oldest'>('newest');
  const [archivePage, setArchivePage] = useState(0);
  const archivePanelRef = useRef<HTMLDivElement>(null);

  const archiveDisplayed = useMemo(() => {
    const q = archiveSearch.trim().toLowerCase();
    const filtered = q ? sessions.filter(s => s.name.toLowerCase().includes(q)) : sessions;
    return [...filtered].sort((a, b) => {
      const ta = a.completed_at_iso ? new Date(a.completed_at_iso).getTime() : 0;
      const tb = b.completed_at_iso ? new Date(b.completed_at_iso).getTime() : 0;
      return archiveSort === 'newest' ? tb - ta : ta - tb;
    });
  }, [sessions, archiveSearch, archiveSort]);

  const archiveTotalPages = Math.ceil(archiveDisplayed.length / ARCHIVE_PAGE_SIZE);

  const archivePageData = useMemo(
    () => archiveDisplayed.slice(archivePage * ARCHIVE_PAGE_SIZE, (archivePage + 1) * ARCHIVE_PAGE_SIZE),
    [archiveDisplayed, archivePage],
  );

  useEffect(() => {
    setArchivePage(0);
  }, [archiveSearch, archiveSort]);

  useEffect(() => {
    if (!isArchiveOpen) return;
    setTimeout(() => archivePanelRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 50);
  }, [archivePage]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <AnimatePresence>
      {sessions.length > 0 && (
        <motion.div
          ref={archivePanelRef}
          key="archive-section"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8, transition: { duration: 0.15 } }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
          className="premium-panel overflow-hidden"
        >
          <button
            onClick={() => {
              const opening = !isArchiveOpen;
              setIsArchiveOpen(opening);
              if (opening) {
                setTimeout(() => archivePanelRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 180);
              } else {
                setArchiveSearch('');
                setArchivePage(0);
              }
            }}
            className="w-full flex items-center justify-between gap-3 px-5 sm:px-6 py-4 transition-colors"
            style={{ background: 'none', border: 'none', cursor: 'pointer', borderBottom: isArchiveOpen ? '1px solid var(--border-subtle)' : 'none' }}
          >
            <div className="flex items-center gap-2">
              <History className="w-5 h-5" style={{ color: 'var(--text-muted)' }} />
              <span className="text-2xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Archivio Sbobine</span>
              <span className="status-pill shrink-0 whitespace-nowrap">{sessions.length}</span>
            </div>
            {isArchiveOpen ? <ChevronUp className="w-4 h-4" style={{ color: 'var(--text-muted)' }} /> : <ChevronDown className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />}
          </button>
          <AnimatePresence>
            {isArchiveOpen && (
              <motion.div
                key="archive-list"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{
                  height: { duration: 0.25, ease: [0.4, 0, 0.2, 1] },
                  opacity: { duration: 0.2, delay: 0.04, ease: 'easeOut' },
                }}
                className="overflow-hidden"
              >
                <div className="px-5 sm:px-6 pt-4 pb-2 flex items-center gap-2">
                  <div className="relative flex-1 flex items-center">
                    <Search className="absolute left-2.5 w-3.5 h-3.5 pointer-events-none" style={{ color: 'var(--text-faint)' }} />
                    <input
                      type="text"
                      value={archiveSearch}
                      onChange={e => setArchiveSearch(e.target.value)}
                      placeholder="Cerca per nome..."
                      className="premium-button-secondary compact-button text-xs pr-3 py-1.5 rounded-[13px] outline-none w-full"
                      style={{ borderColor: 'var(--border-default)', background: 'rgba(255,255,255,0.03)', color: 'var(--text-primary)', paddingLeft: '2rem' }}
                    />
                  </div>
                  <button
                    onClick={() => setArchiveSort(s => s === 'newest' ? 'oldest' : 'newest')}
                    className="premium-button-secondary compact-button text-xs px-2.5 py-1.5 rounded-[13px] flex items-center gap-1 shrink-0"
                    style={{ color: 'var(--text-muted)', borderColor: 'var(--border-default)' }}
                    title={archiveSort === 'newest' ? 'Ordinate: più recenti prima' : 'Ordinate: più vecchie prima'}
                  >
                    {archiveSort === 'newest' ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
                    <span>{archiveSort === 'newest' ? 'Recente' : 'Vecchia'}</span>
                  </button>
                </div>
                <div className="px-5 sm:px-6 pb-4 flex flex-col gap-2">
                  <AnimatePresence mode="popLayout">
                    {archivePageData.map((session) => {
                      const ts = session.completed_at_iso ? new Date(session.completed_at_iso).getTime() : 0;
                      return (
                        <motion.div
                          key={session.session_dir}
                          initial={{ opacity: 0, y: 6 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -4, transition: { duration: 0.1 } }}
                          transition={{ duration: 0.18, ease: 'easeOut' }}
                          onClick={() => onPreview(session.html_path, session.name, session.input_path, undefined, session.session_dir)}
                          className="flex items-center justify-between gap-3 rounded-xl px-4 py-3 cursor-pointer transition-colors bg-white/[0.02] hover:bg-white/[0.05]"
                          style={{ border: '1px solid var(--border-subtle)' }}
                        >
                          <div className="flex items-center gap-3 overflow-hidden flex-1">
                            <History className="w-4 h-4 shrink-0" style={{ color: 'var(--text-faint)' }} />
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{session.name}</p>
                              <div className="flex flex-wrap items-center gap-2 mt-0.5 text-xs" style={{ color: 'var(--text-muted)' }}>
                                {ts > 0 && <span>{formatRelativeTime(ts)}</span>}
                                {session.effective_model && (
                                  <><span className="w-1 h-1 rounded-full" style={{ background: 'var(--border-default)' }} /><span>{shortModelName(session.effective_model)}</span></>
                                )}
                              </div>
                              <div
                                className="mt-0.5 flex items-center gap-1 text-[11px] hover:underline"
                                style={{ color: 'var(--text-faint)', cursor: 'pointer' }}
                                onClick={(e) => { e.stopPropagation(); onOpenFile(session.html_path.replace(/[/\\][^/\\]+$/, '') || session.html_path); }}
                                title={`Apri cartella: ${session.html_path.replace(/[/\\][^/\\]+$/, '') || session.html_path}`}
                              >
                                <FolderOpen className="w-3 h-3 shrink-0" />
                                <span className="truncate">
                                  {session.html_path.replace(/\\/g, '/').split('/').slice(-2).join('/')}
                                </span>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-1 shrink-0">
                            <button
                              onClick={e => { e.stopPropagation(); onOpenFile(session.html_path); }}
                              className="icon-button compact-icon-button"
                              style={{ color: 'var(--text-muted)' }}
                              title="Apri nel browser"
                              aria-label="Apri nel browser"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={e => { e.stopPropagation(); onDeleteSession(session.session_dir, session.name); }}
                              className="icon-button compact-icon-button"
                              style={{ color: 'var(--error-text)', borderColor: 'var(--error-ring)', background: 'var(--error-subtle)' }}
                              title="Elimina sessione"
                              aria-label="Elimina sessione"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </motion.div>
                      );
                    })}
                    {archiveSearch.trim() && archiveDisplayed.length === 0 && (
                      <motion.p
                        key="no-results"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.15 }}
                        className="text-sm text-center py-4"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        Nessun risultato per &ldquo;{archiveSearch}&rdquo;
                      </motion.p>
                    )}
                  </AnimatePresence>
                  {archiveTotalPages > 1 && (
                    <div className="flex items-center justify-center gap-3 pt-2">
                      <button
                        onClick={() => setArchivePage(p => Math.max(0, p - 1))}
                        disabled={archivePage === 0}
                        className="icon-button compact-icon-button"
                        style={{ color: 'var(--text-muted)', opacity: archivePage === 0 ? 0.35 : 1 }}
                        aria-label="Pagina precedente"
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </button>
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                        {archivePage + 1} / {archiveTotalPages}
                      </span>
                      <button
                        onClick={() => setArchivePage(p => Math.min(archiveTotalPages - 1, p + 1))}
                        disabled={archivePage >= archiveTotalPages - 1}
                        className="icon-button compact-icon-button"
                        style={{ color: 'var(--text-muted)', opacity: archivePage >= archiveTotalPages - 1 ? 0.35 : 1 }}
                        aria-label="Pagina successiva"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
