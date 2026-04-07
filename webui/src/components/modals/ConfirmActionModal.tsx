import { AnimatePresence, motion } from 'motion/react';
import { AlertTriangle, X } from 'lucide-react';

interface ConfirmActionModalProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  onClose: () => void;
  onConfirm: () => void;
}

export function ConfirmActionModal({
  isOpen,
  title,
  description,
  confirmLabel,
  cancelLabel = 'Annulla',
  onClose,
  onConfirm,
}: ConfirmActionModalProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
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
                <AlertTriangle className="w-5 h-5 shrink-0" style={{ color: 'var(--error-text)' }} />
                <h2 className="text-lg font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
                  {title}
                </h2>
              </div>
              <button
                onClick={onClose}
                className="icon-button modal-icon-button"
                style={{ color: 'var(--text-muted)' }}
                aria-label="Chiudi finestra"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-5 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <p>{description}</p>
            </div>
            <div className="px-5 py-4 flex gap-3 shrink-0" style={{ background: 'var(--bg-elevated)', borderTop: '1px solid var(--border-subtle)' }}>
              <button onClick={onClose} className="modal-action-button flex-1">
                {cancelLabel}
              </button>
              <button
                onClick={onConfirm}
                className="modal-action-button is-danger flex-1"
              >
                {confirmLabel}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
