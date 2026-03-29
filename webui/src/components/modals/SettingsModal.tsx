import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { AlertCircle, Eye, EyeOff, HardDrive, Settings, X } from 'lucide-react';
import type { ValidationResult } from '../../bridge';
import { formatSize } from '../../utils';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiKey: string;
  setApiKey: (key: string) => void;
  fallbackKeys: string[];
  setFallbackKeys: (keys: string[]) => void;
  appendConsole: (msg: string) => void;
}

export function SettingsModal({
  isOpen, onClose, apiKey, setApiKey, fallbackKeys, setFallbackKeys, appendConsole,
}: SettingsModalProps) {
  const [showApiKeys, setShowApiKeys] = useState(false);
  const [sessionInfo, setSessionInfo] = useState<{ total_bytes: number; total_sessions: number } | null>(null);
  const [isLoadingSessionInfo, setIsLoadingSessionInfo] = useState(false);
  const [isCleaningSession, setIsCleaningSession] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<{ removed: number; freed_bytes: number } | null>(null);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [isValidatingEnvironment, setIsValidatingEnvironment] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setCleanupResult(null);
    if (!window.pywebview?.api?.get_session_storage_info) return;
    setIsLoadingSessionInfo(true);
    setSessionInfo(null);
    window.pywebview.api.get_session_storage_info()
      .then(res => { if (res?.ok) setSessionInfo({ total_bytes: res.total_bytes ?? 0, total_sessions: res.total_sessions ?? 0 }); })
      .catch(() => {})
      .finally(() => setIsLoadingSessionInfo(false));
  }, [isOpen]);

  const handleCleanupSessions = async () => {
    if (!window.pywebview?.api?.cleanup_old_sessions) return;
    setIsCleaningSession(true);
    setCleanupResult(null);
    try {
      const res = await window.pywebview.api.cleanup_old_sessions(30);
      if (res?.ok) {
        setCleanupResult({ removed: res.removed ?? 0, freed_bytes: res.freed_bytes ?? 0 });
        if (window.pywebview?.api?.get_session_storage_info) {
          const info = await window.pywebview.api.get_session_storage_info();
          if (info?.ok) setSessionInfo({ total_bytes: info.total_bytes ?? 0, total_sessions: info.total_sessions ?? 0 });
        }
      } else {
        appendConsole(`❌ Pulizia sessioni fallita: ${res?.error || 'errore sconosciuto'}`);
      }
    } catch (e: any) {
      appendConsole(`❌ Pulizia sessioni fallita: ${e?.message || e}`);
    }
    setIsCleaningSession(false);
  };

  const runEnvironmentValidation = async () => {
    if (!window.pywebview?.api?.validate_environment) return;
    setIsValidatingEnvironment(true);
    try {
      const response = await window.pywebview.api.validate_environment(apiKey.trim(), Boolean(apiKey.trim()));
      if (!response?.ok || !response.result) {
        appendConsole(`❌ Validazione ambiente fallita: ${response?.error || 'errore sconosciuto'}`);
        setValidationResult(null);
        return;
      }
      setValidationResult(response.result);
      appendConsole(response.result.summary);
    } catch (error: any) {
      appendConsole(`❌ Validazione ambiente fallita: ${error?.message || error}`);
      setValidationResult(null);
    } finally {
      setIsValidatingEnvironment(false);
    }
  };

  const saveSettings = async () => {
    if (window.pywebview?.api) {
      const keys = fallbackKeys.map(k => k.trim()).filter(Boolean);
      const result = await window.pywebview.api.save_settings(apiKey.trim(), keys);
      if (!result?.ok) {
        appendConsole(`❌ Errore salvataggio impostazioni: ${result?.error || 'errore sconosciuto'}`);
        return;
      }
    }
    onClose();
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
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
            <div className="flex items-center justify-between px-5 py-4 shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
                <Settings className="w-5 h-5" style={{ color: 'var(--text-muted)' }} /> Impostazioni
              </h2>
              <button
                onClick={onClose}
                className="icon-button h-10 w-10 rounded-[14px]"
                style={{ color: 'var(--text-muted)' }}
                aria-label="Chiudi impostazioni"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="app-scroll flex-1 overflow-y-auto overflow-x-hidden px-5 py-5 space-y-6">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>Google Gemini API Key (Principale)</label>
                  <button
                    onClick={() => setShowApiKeys(!showApiKeys)}
                    className="icon-button h-9 w-9"
                    style={{ color: 'var(--text-muted)' }}
                    title={showApiKeys ? 'Nascondi chiave' : 'Mostra chiave'}
                  >
                    {showApiKeys ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <input
                  type={showApiKeys ? 'text' : 'password'}
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder="AIzaSy..."
                  className="app-input font-mono text-sm"
                  style={{ background: 'var(--bg-input)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }}
                />
                <p className="text-xs mt-2 flex items-start gap-1.5" style={{ color: 'var(--text-muted)' }}>
                  <AlertCircle className="w-4 h-4 shrink-0" /> Salvata in modo sicuro tramite DPAPI (Windows) o Keyring (Mac/Linux).
                </p>
                <a
                  href="#"
                  onClick={e => { e.preventDefault(); window.pywebview?.api?.open_url?.('https://aistudio.google.com/apikey'); }}
                  className="text-xs mt-1 inline-flex items-center gap-1 hover:opacity-100 opacity-70"
                  style={{ color: 'var(--accent-text, var(--text-secondary))' }}
                >
                  → Ottieni gratis su aistudio.google.com
                </a>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>API Keys di Riserva (Fallback)</label>
                  <button
                    onClick={() => setShowApiKeys(!showApiKeys)}
                    className="icon-button h-9 w-9"
                    style={{ color: 'var(--text-muted)' }}
                    title={showApiKeys ? 'Nascondi chiavi' : 'Mostra chiavi'}
                  >
                    {showApiKeys ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <textarea
                  value={fallbackKeys.join('\n')}
                  onChange={e => setFallbackKeys(e.target.value.split('\n'))}
                  placeholder="Inserisci una API Key per riga..."
                  rows={3}
                  className={`app-textarea font-mono text-sm ${!showApiKeys ? 'obscured-text' : ''}`}
                  style={{ background: 'var(--bg-input)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }}
                />
                <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>Usate automaticamente in caso di esaurimento quota (429).</p>
              </div>
              <div className="pt-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-muted)' }}>Avanzate (Sola Lettura)</h3>
                <ul className="space-y-2 text-sm" style={{ color: 'var(--text-muted)' }}>
                  <li className="flex justify-between"><span>Modello:</span> <span style={{ color: 'var(--text-secondary)' }}>gemini-2.5-flash</span></li>
                  <li className="flex justify-between"><span>Chunk:</span> <span style={{ color: 'var(--text-secondary)' }}>15 minuti</span></li>
                  <li className="flex justify-between"><span>Overlap:</span> <span style={{ color: 'var(--text-secondary)' }}>30 secondi</span></li>
                  <li className="flex justify-between"><span>Pre-conversione:</span> <span style={{ color: 'var(--text-secondary)' }}>Mono 16kHz 48k</span></li>
                </ul>
              </div>
              <div className="pt-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <div className="flex items-center justify-between gap-3 mb-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                    <HardDrive className="w-3.5 h-3.5" />
                    Sessioni salvate
                  </h3>
                  {sessionInfo !== null && (
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      {sessionInfo.total_sessions} {sessionInfo.total_sessions === 1 ? 'sessione' : 'sessioni'}
                    </span>
                  )}
                </div>
                <div className="rounded-xl px-4 py-3 space-y-3" style={{ background: 'var(--bg-input)', border: '1px solid var(--border-subtle)' }}>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Spazio occupato</p>
                      <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                        {isLoadingSessionInfo ? 'Calcolo…' : sessionInfo !== null ? formatSize(sessionInfo.total_bytes) : '—'}
                      </p>
                    </div>
                    <button
                      onClick={handleCleanupSessions}
                      disabled={isCleaningSession || isLoadingSessionInfo}
                      className="premium-button-secondary compact-button px-3 py-1.5 text-[11px] rounded-[13px] disabled:opacity-50"
                      style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border-default)' }}
                    >
                      {isCleaningSession ? 'Pulizia…' : 'Pulisci (> 30 giorni)'}
                    </button>
                  </div>
                  {cleanupResult !== null && (
                    <p className="text-xs" style={{ color: cleanupResult.removed > 0 ? 'var(--success-text)' : 'var(--text-muted)' }}>
                      {cleanupResult.removed > 0
                        ? `Rimoss${cleanupResult.removed === 1 ? 'a' : 'e'} ${cleanupResult.removed} ${cleanupResult.removed === 1 ? 'sessione' : 'sessioni'}, liberati ${formatSize(cleanupResult.freed_bytes)}.`
                        : 'Nessuna sessione da pulire (tutte recenti o cartella vuota).'}
                    </p>
                  )}
                  <p className="text-xs" style={{ color: 'var(--text-faint, var(--text-muted))' }}>
                    Progressi intermedi per riprendere elaborazioni interrotte. La pulizia rimuove le sessioni non toccate da oltre 30 giorni.
                  </p>
                </div>
              </div>
              <div className="pt-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <div className="flex items-center justify-between gap-3 mb-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>Verifica Ambiente</h3>
                  <button
                    onClick={runEnvironmentValidation}
                    disabled={isValidatingEnvironment}
                    className="premium-button-secondary compact-button px-3 py-1.5 text-[11px] rounded-[13px]"
                    style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border-default)' }}
                  >
                    {isValidatingEnvironment ? 'Verifica...' : 'Verifica ambiente'}
                  </button>
                </div>
                {validationResult && (
                  <div className="space-y-2 text-sm">
                    <p style={{ color: validationResult.ok ? 'var(--success-text)' : 'var(--error-text)' }}>{validationResult.summary}</p>
                    {validationResult.checks.map(check => (
                      <div key={check.id} className="rounded-lg px-3 py-2 overflow-hidden" style={{ background: 'var(--bg-input)', border: '1px solid var(--border-subtle)' }}>
                        <div className="flex items-center justify-between gap-3">
                          <span style={{ color: 'var(--text-primary)' }}>{check.label}</span>
                          <span style={{ color: check.status === 'ok' ? 'var(--success-text)' : check.status === 'warning' ? 'var(--warning-text)' : 'var(--error-text)' }}>
                            {check.status.toUpperCase()}
                          </span>
                        </div>
                        <p className="mt-1" style={{ color: 'var(--text-secondary)' }}>{check.message}</p>
                        {check.details && (
                          <p className="mt-1 text-xs font-mono break-all whitespace-pre-wrap" style={{ color: 'var(--text-muted)', overflowWrap: 'anywhere' }}>
                            {check.details}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="px-5 py-4 shrink-0" style={{ background: 'var(--bg-elevated)', borderTop: '1px solid var(--border-subtle)' }}>
              <button
                onClick={saveSettings}
                className="w-full py-3 font-medium rounded-xl transition-colors"
                style={{ background: 'var(--btn-primary-bg)', color: 'var(--btn-primary-text)' }}
              >
                Salva e Chiudi
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
