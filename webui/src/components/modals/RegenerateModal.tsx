import { motion, AnimatePresence } from 'motion/react';
import { AlertCircle, X } from 'lucide-react';

interface RegenerateModalProps {
  prompt: { filename: string; mode?: 'completed' | 'resume' } | null;
  onAnswer: (yes: boolean) => void;
  onDismiss: () => void;
}

export function RegenerateModal({ prompt, onAnswer, onDismiss }: RegenerateModalProps) {
  return (
    <AnimatePresence>
      {prompt && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onDismiss}
            className="absolute inset-0"
            style={{ background: 'var(--bg-overlay)', backdropFilter: 'blur(10px)' }}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="modal-card relative w-full max-w-md max-h-[86vh] overflow-hidden flex flex-col"
          >
            <div className="flex items-center justify-between gap-3 px-5 py-4 shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <div className="flex items-center gap-3 min-w-0">
                <AlertCircle className="w-5 h-5 shrink-0" style={{ color: 'var(--warning-text)' }} />
                <h2 className="text-lg font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
                  {prompt.mode === 'completed' ? 'Versione già pronta' : 'Ripresa disponibile'}
                </h2>
              </div>
              <button
                onClick={onDismiss}
                className="icon-button modal-icon-button"
                style={{ color: 'var(--text-muted)' }}
                aria-label="Chiudi finestra"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <p>
                {prompt.mode === 'completed'
                  ? <><strong style={{ color: 'var(--text-primary)' }}>{prompt.filename}</strong> {' '}risulta già completato.</>
                  : <>Per il file <strong style={{ color: 'var(--text-primary)' }}>{prompt.filename}</strong> ci sono progressi salvati e pronti per essere ripresi.</>}
              </p>
              <p>
                {prompt.mode === 'completed'
                  ? 'Puoi usare la versione già pronta oppure rigenerare tutto da zero.'
                  : 'Puoi riprendere da dove eri rimasto oppure ricominciare da zero perdendo i progressi salvati.'}
              </p>
            </div>
            <div className="px-5 py-4 flex gap-3 shrink-0" style={{ background: 'var(--bg-elevated)', borderTop: '1px solid var(--border-subtle)' }}>
              <button onClick={() => onAnswer(false)} className="modal-action-button flex-1">
                {prompt.mode === 'completed' ? 'Usa versione pronta' : 'Riprendi da dove eri rimasto'}
              </button>
              <button onClick={() => onAnswer(true)} className="modal-action-button is-danger flex-1">
                {prompt.mode === 'completed' ? 'Rigenera da zero' : 'Ricomincia da zero'}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
