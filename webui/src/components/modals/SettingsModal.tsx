import { createPortal } from 'react-dom';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Activity, AlertCircle, ArrowDown, ArrowUp, ChevronDown, Cpu, Eye, EyeOff, HardDrive, Settings, SlidersHorizontal, X } from 'lucide-react';
import type { ModelOption, ValidationResult } from '../../bridge';
import { formatSize, GEMINI_KEY_PATTERN } from '../../utils';

const SESSION_CLEANUP_DAYS = 14;

interface CustomSelectOption {
  value: string;
  label: string;
}

interface CustomSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: CustomSelectOption[];
  placeholder?: string;
}

function CustomSelect({ value, onChange, options, placeholder }: CustomSelectProps) {
  const [open, setOpen] = useState(false);
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});
  const buttonRef = useRef<HTMLButtonElement>(null);

  const updatePosition = useCallback(() => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownStyle({ position: 'fixed', top: rect.bottom + 4, left: rect.left, width: rect.width, zIndex: 9999 });
    }
  }, []);

  const toggleDropdown = () => setOpen(prev => !prev);

  useLayoutEffect(() => {
    if (!open) return;
    updatePosition();
    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);
    return () => {
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return;
    const handleMouseDown = (e: MouseEvent) => {
      if (buttonRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [open]);

  const selectedLabel = options.find(o => o.value === value)?.label;
  const displayLabel = selectedLabel ?? placeholder ?? '';

  const dropdown = open ? createPortal(
    <div
      onMouseDown={e => e.stopPropagation()}
      style={{
        ...dropdownStyle,
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-default)',
        boxShadow: 'var(--shadow-strong)',
        borderRadius: '14px',
        overflow: 'auto',
        maxHeight: '220px',
      }}
    >
      {placeholder && (
        <button
          type="button"
          onClick={() => { onChange(''); setOpen(false); }}
          className="w-full text-left px-4 py-1.5 text-xs"
          style={{ color: 'var(--text-muted)' }}
        >
          {placeholder}
        </button>
      )}
      {options.map(opt => (
        <button
          key={opt.value}
          type="button"
          onClick={() => { onChange(opt.value); setOpen(false); }}
          className="w-full text-left px-4 py-1.5 text-xs transition-colors"
          style={{
            color: opt.value === value ? 'var(--text-primary)' : 'var(--text-secondary)',
            background: opt.value === value ? 'var(--accent-subtle)' : undefined,
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--accent-subtle)'; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = opt.value === value ? 'var(--accent-subtle)' : ''; }}
        >
          {opt.label}
        </button>
      ))}
    </div>,
    document.body,
  ) : null;

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={toggleDropdown}
        className="app-input text-xs flex items-center justify-between gap-2 cursor-pointer"
        style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-default)',
          color: selectedLabel ? 'var(--text-primary)' : 'var(--text-muted)',
          textAlign: 'left',
          padding: '0.35rem 0.75rem',
        }}
      >
        <span className="truncate flex-1">{displayLabel}</span>
        <ChevronDown
          className="w-4 h-4 shrink-0 transition-transform"
          style={{
            color: 'var(--text-muted)',
            transform: open ? 'rotate(180deg)' : undefined,
          }}
        />
      </button>
      {dropdown}
    </>
  );
}

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiKey: string;
  setApiKey: (key: string) => void;
  fallbackKeys: string[];
  setFallbackKeys: (keys: string[]) => void;
  preferredModel: string;
  setPreferredModel: (model: string) => void;
  fallbackModels: string[];
  setFallbackModels: (models: string[]) => void;
  availableModels: ModelOption[];
  appendConsole: (msg: string) => void;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function SettingsModal({
  isOpen,
  onClose,
  apiKey,
  setApiKey,
  fallbackKeys,
  setFallbackKeys,
  preferredModel,
  setPreferredModel,
  fallbackModels,
  setFallbackModels,
  availableModels,
  appendConsole,
}: SettingsModalProps) {
  const [showApiKeys, setShowApiKeys] = useState(false);
  const [sessionInfo, setSessionInfo] = useState<{ total_bytes: number; total_sessions: number } | null>(null);
  const [isLoadingSessionInfo, setIsLoadingSessionInfo] = useState(false);
  const [isCleaningSession, setIsCleaningSession] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<{ removed: number; freed_bytes: number } | null>(null);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [isValidatingEnvironment, setIsValidatingEnvironment] = useState(false);
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const isSavingRef = useRef(false);
  const [isSaving, setIsSaving] = useState(false);
  const handleClose = () => { if (isSavingRef.current) return; onClose(); };

  useEffect(() => {
    if (!isOpen) { setIsAdvancedOpen(false); setIsSaving(false); isSavingRef.current = false; return; }
    setSaveError(null);
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
      const res = await window.pywebview.api.cleanup_old_sessions(SESSION_CLEANUP_DAYS);
      if (res?.ok) {
        setCleanupResult({ removed: res.removed ?? 0, freed_bytes: res.freed_bytes ?? 0 });
        if (window.pywebview?.api?.get_session_storage_info) {
          const info = await window.pywebview.api.get_session_storage_info();
          if (info?.ok) setSessionInfo({ total_bytes: info.total_bytes ?? 0, total_sessions: info.total_sessions ?? 0 });
        }
      } else {
        appendConsole(`❌ Pulizia sessioni fallita: ${res?.error || 'errore sconosciuto'}`);
      }
    } catch (e: unknown) {
      appendConsole(`❌ Pulizia sessioni fallita: ${getErrorMessage(e)}`);
    }
    setIsCleaningSession(false);
  };

  const runEnvironmentValidation = async () => {
    if (!window.pywebview?.api?.validate_environment) return;
    setIsValidatingEnvironment(true);
    try {
      const response = await window.pywebview.api.validate_environment(
        apiKey.trim(),
        Boolean(apiKey.trim()),
        preferredModel,
        fallbackModels,
      );
      if (!response?.ok || !response.result) {
        appendConsole(`❌ Validazione ambiente fallita: ${response?.error || 'errore sconosciuto'}`);
        setValidationResult(null);
        return;
      }
      setValidationResult(response.result);
      appendConsole(response.result.summary);
    } catch (error: unknown) {
      appendConsole(`❌ Validazione ambiente fallita: ${getErrorMessage(error)}`);
      setValidationResult(null);
    } finally {
      setIsValidatingEnvironment(false);
    }
  };

  const saveSettings = async () => {
    if (isSavingRef.current) return;
    isSavingRef.current = true;
    setIsSaving(true);
    setSaveError(null);
    try {
      if (!window.pywebview?.api?.save_settings) {
        const err = 'Bridge Python non disponibile — impostazioni non salvate.';
        setSaveError(err);
        appendConsole(`❌ ${err}`);
        return;
      }
      const keys = fallbackKeys.map(k => k.trim()).filter(Boolean);
      let result;
      try {
        result = await window.pywebview.api.save_settings(apiKey.trim(), keys, preferredModel, fallbackModels);
      } catch (e: unknown) {
        const err = `Errore salvataggio impostazioni: ${getErrorMessage(e)}`;
        setSaveError(err);
        appendConsole(`❌ ${err}`);
        return;
      }
      if (!result?.ok) {
        const err = `Errore salvataggio impostazioni: ${result?.error || 'errore sconosciuto'}`;
        setSaveError(err);
        appendConsole(`❌ ${err}`);
        return;
      }
      onClose();
    } finally {
      isSavingRef.current = false;
      setIsSaving(false);
    }
  };

  const availableFallbackOptions = availableModels.filter(model => model.id !== preferredModel);
  const selectedModelSummaries = [preferredModel, ...fallbackModels]
    .map(modelId => availableModels.find(option => option.id === modelId))
    .filter(Boolean) as ModelOption[];
  const defaultChunkMinutes = availableModels.find(m => m.id === preferredModel)?.default_chunk_minutes ?? 15;

  const handlePrimaryModelChange = (nextPrimary: string) => {
    setPreferredModel(nextPrimary);
    setFallbackModels(fallbackModels.filter(modelId => modelId !== nextPrimary));
  };

  const handleAddFallbackModel = (nextFallback: string) => {
    if (!nextFallback || nextFallback === preferredModel || fallbackModels.includes(nextFallback)) return;
    setFallbackModels([...fallbackModels, nextFallback]);
  };

  const moveFallbackModel = (index: number, direction: -1 | 1) => {
    const nextIndex = index + direction;
    if (index < 0 || nextIndex < 0 || nextIndex >= fallbackModels.length) return;
    const nextModels = [...fallbackModels];
    const [moved] = nextModels.splice(index, 1);
    nextModels.splice(nextIndex, 0, moved);
    setFallbackModels(nextModels);
  };

  const removeFallbackModel = (modelId: string) => {
    setFallbackModels(fallbackModels.filter(item => item !== modelId));
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={handleClose}
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
                onClick={handleClose}
                disabled={isSaving}
                className="icon-button modal-icon-button"
                style={{ color: 'var(--text-muted)' }}
                aria-label="Chiudi impostazioni"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="app-scroll flex-1 overflow-y-auto overflow-x-hidden px-5 py-5 space-y-6">
              {/* 1. API Key + inline validation */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>Google Gemini API Key (Principale)</label>
                  <button
                    onClick={() => setShowApiKeys(!showApiKeys)}
                    className="opacity-50 hover:opacity-100 transition-opacity"
                    style={{ color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', lineHeight: 1, padding: '2px' }}
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
                {apiKey.trim() && (
                  <p className="text-xs mt-1.5" style={{ color: GEMINI_KEY_PATTERN.test(apiKey.trim()) ? 'var(--success-text)' : 'var(--warning-text)' }}>
                    {GEMINI_KEY_PATTERN.test(apiKey.trim()) ? '✓ Formato valido' : '⚠ Formato non valido — le chiavi iniziano con AIzaSy...'}
                  </p>
                )}
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

              {/* 2. Fallback Keys */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>API Keys di Riserva (Fallback)</label>
                  <button
                    onClick={() => setShowApiKeys(!showApiKeys)}
                    className="opacity-50 hover:opacity-100 transition-opacity"
                    style={{ color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', lineHeight: 1, padding: '2px' }}
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

              {/* Avanzati */}
              <div className="pt-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <button
                  type="button"
                  onClick={() => setIsAdvancedOpen(v => !v)}
                  className="w-full flex items-center justify-between"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                >
                  <h3 className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                    <SlidersHorizontal className="w-3.5 h-3.5" />
                    Avanzati
                  </h3>
                  <ChevronDown
                    className="w-4 h-4 shrink-0 transition-transform"
                    style={{ color: 'var(--text-muted)', transform: isAdvancedOpen ? 'rotate(180deg)' : undefined }}
                  />
                </button>
                <AnimatePresence initial={false}>
                  {isAdvancedOpen && (
                    <motion.div
                      key="advanced-panel"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2, ease: 'easeInOut' }}
                      style={{ overflow: 'hidden' }}
                    >
                      <div className="space-y-6 pt-4">
                        {/* Modello Gemini */}
                        <div>
                          <div className="flex items-center justify-between gap-3 mb-3">
                            <h3 className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                              <Cpu className="w-3.5 h-3.5" />
                              Modello Gemini
                            </h3>
                          </div>
                          <div className="rounded-xl px-4 py-3 space-y-5" style={{ background: 'var(--bg-input)', border: '1px solid var(--border-subtle)' }}>
                            <div className="space-y-4">
                              <label className="text-sm font-medium" style={{ color: 'var(--text-secondary)', display: 'block', marginBottom: '10px' }}>Modello primario</label>
                              <CustomSelect
                                value={preferredModel}
                                onChange={handlePrimaryModelChange}
                                options={availableModels.map(m => ({ value: m.id, label: m.label }))}
                              />
                            </div>
                            <div className="space-y-4">
                              <label className="text-sm font-medium" style={{ color: 'var(--text-secondary)', display: 'block', marginBottom: '10px' }}>Fallback modelli (solo su 503)</label>
                              <CustomSelect
                                value=""
                                onChange={val => { if (val) handleAddFallbackModel(val); }}
                                options={availableFallbackOptions
                                  .filter(model => !fallbackModels.includes(model.id))
                                  .map(m => ({ value: m.id, label: m.label }))}
                                placeholder="Aggiungi un fallback..."
                              />
                              {fallbackModels.length > 0 ? (
                                <div className="space-y-2">
                                  {fallbackModels.map((modelId, index) => {
                                    const model = availableModels.find(option => option.id === modelId);
                                    if (!model) return null;
                                    return (
                                      <div
                                        key={modelId}
                                        className="rounded-lg px-3 py-2 flex items-start justify-between gap-3"
                                        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}
                                      >
                                        <div className="min-w-0">
                                          <p className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{model.label}</p>
                                          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{model.summary}</p>
                                        </div>
                                        <div className="flex items-center gap-1 shrink-0">
                                          <button
                                            onClick={() => moveFallbackModel(index, -1)}
                                            disabled={index === 0}
                                            className="icon-button modal-icon-button disabled:opacity-40"
                                            style={{ color: 'var(--text-muted)' }}
                                            title="Sposta su"
                                          >
                                            <ArrowUp className="w-4 h-4" />
                                          </button>
                                          <button
                                            onClick={() => moveFallbackModel(index, 1)}
                                            disabled={index === fallbackModels.length - 1}
                                            className="icon-button modal-icon-button disabled:opacity-40"
                                            style={{ color: 'var(--text-muted)' }}
                                            title="Sposta giu"
                                          >
                                            <ArrowDown className="w-4 h-4" />
                                          </button>
                                          <button
                                            onClick={() => removeFallbackModel(modelId)}
                                            className="icon-button modal-icon-button"
                                            style={{ color: 'var(--text-muted)' }}
                                            title="Rimuovi fallback"
                                          >
                                            <X className="w-4 h-4" />
                                          </button>
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              ) : (
                                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                                  Nessun fallback aggiuntivo configurato oltre al primario.
                                </p>
                              )}
                            </div>
                            <p className="text-xs" style={{ color: 'var(--text-faint, var(--text-muted))' }}>
                              L'app cambia modello solo se il modello corrente risponde 503/UNAVAILABLE. Se passa a un fallback, resta su quello fino alla fine del job.
                            </p>
                          </div>
                        </div>

                        {/* Sessioni salvate */}
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
                                className="modal-action-button is-compact disabled:opacity-50"
                                style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)' }}
                              >
                                {isCleaningSession ? 'Pulizia…' : `Pulisci (> ${SESSION_CLEANUP_DAYS} giorni)`}
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
                              Progressi intermedi per riprendere elaborazioni interrotte. La pulizia rimuove le sessioni non toccate da oltre {SESSION_CLEANUP_DAYS} giorni.
                            </p>
                          </div>
                        </div>

                        {/* Diagnostica */}
                        <div className="pt-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                          <div className="flex items-center justify-between gap-3 mb-3">
                            <h3 className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                              <Activity className="w-3.5 h-3.5" />
                              Diagnostica
                            </h3>
                            <button
                              onClick={runEnvironmentValidation}
                              disabled={isValidatingEnvironment}
                              className="modal-action-button is-compact"
                              style={{ background: 'var(--bg-surface)', color: 'var(--text-secondary)' }}
                            >
                              {isValidatingEnvironment ? 'Verifica...' : 'Verifica ambiente'}
                            </button>
                          </div>
                          <ul className="space-y-1.5 mb-3">
                            <li className="flex justify-between text-xs" style={{ color: 'var(--text-faint)' }}><span>Modello primario:</span> <span className="font-mono">{preferredModel}</span></li>
                            <li className="flex justify-between text-xs" style={{ color: 'var(--text-faint)' }}><span>Fallback:</span> <span className="font-mono">{fallbackModels.join(' -> ') || 'nessuno'}</span></li>
                            <li className="flex justify-between text-xs" style={{ color: 'var(--text-faint)' }}><span>Chunk:</span> <span className="font-mono">{defaultChunkMinutes} min</span></li>
                            <li className="flex justify-between text-xs" style={{ color: 'var(--text-faint)' }}><span>Overlap:</span> <span className="font-mono">30 s</span></li>
                            <li className="flex justify-between text-xs" style={{ color: 'var(--text-faint)' }}><span>Pre-conversione:</span> <span className="font-mono">Mono 16kHz 48k</span></li>
                          </ul>
                          {selectedModelSummaries.length > 0 && (
                            <div className="space-y-2 mb-3">
                              {selectedModelSummaries.map(model => (
                                <div key={model.id} className="rounded-lg px-3 py-2" style={{ background: 'var(--bg-input)', border: '1px solid var(--border-subtle)' }}>
                                  <p className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{model.label}</p>
                                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{model.summary}</p>
                                </div>
                              ))}
                            </div>
                          )}
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
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
            <div className="px-5 py-4 shrink-0" style={{ background: 'var(--bg-elevated)', borderTop: '1px solid var(--border-subtle)' }}>
              {saveError && (
                <p className="text-xs mb-3" style={{ color: 'var(--error-text)' }}>{saveError}</p>
              )}
              <button
                onClick={saveSettings}
                disabled={isSaving}
                className="modal-action-button is-primary w-full"
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
