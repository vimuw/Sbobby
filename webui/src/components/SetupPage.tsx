import { useState } from 'react';
import { Eye, EyeOff, Key, Settings } from 'lucide-react';
import { GEMINI_KEY_PATTERN } from '../utils';

interface SetupPageProps {
  hasProtectedKey: boolean;
  setIsSettingsOpen: (v: boolean) => void;
  onSaved: (key: string) => void;
  preferredModel: string;
  fallbackKeys: string[];
  fallbackModels: string[];
}

export function SetupPage({ hasProtectedKey, setIsSettingsOpen, onSaved, preferredModel, fallbackKeys, fallbackModels }: SetupPageProps) {
  const [setupKeyInput, setSetupKeyInput] = useState('');
  const [setupKeyShowRaw, setSetupKeyShowRaw] = useState(false);
  const [setupKeySaving, setSetupKeySaving] = useState(false);
  const [setupKeyError, setSetupKeyError] = useState<string | null>(null);

  const handleSetupSave = async () => {
    setSetupKeySaving(true);
    setSetupKeyError(null);
    try {
      if (!window.pywebview?.api?.save_settings) {
        setSetupKeyError('Bridge Python non disponibile — impostazioni non salvate.');
        return;
      }
      let result;
      try {
        result = await window.pywebview.api.save_settings(setupKeyInput.trim(), fallbackKeys, preferredModel, fallbackModels);
      } catch (e: unknown) {
        setSetupKeyError(`Errore salvataggio: ${e instanceof Error ? e.message : String(e)}`);
        return;
      }
      if (!result?.ok) {
        setSetupKeyError(`Errore salvataggio: ${result?.error || 'errore sconosciuto'}`);
        return;
      }
      onSaved(setupKeyInput.trim());
    } finally {
      setSetupKeySaving(false);
    }
  };

  return (
    <div
      className="relative overflow-hidden rounded-2xl px-8 py-10 flex flex-col items-center gap-5"
      style={{ background: 'rgba(255,255,255,0.02)', border: '1.5px solid var(--border-default)' }}
    >
      <div className="flex flex-col items-center gap-2 text-center">
        <div className="w-14 h-14 rounded-full flex items-center justify-center shadow-xl" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-default)' }}>
          <Key className="w-7 h-7" style={{ color: 'var(--text-muted)' }} />
        </div>
        <h3 className="text-lg font-semibold mt-1" style={{ color: 'var(--text-primary)' }}>{hasProtectedKey ? 'Chiave API non accessibile' : 'Configura la tua API Key'}</h3>
        <p className="text-sm leading-relaxed max-w-sm" style={{ color: 'var(--text-muted)' }}>
          {hasProtectedKey
            ? 'La tua chiave era salvata ma non è accessibile (errore di sistema). Reinseriscila per continuare.'
            : 'El Sbobinator usa Google Gemini per trascrivere audio e video. Inserisci una chiave API gratuita per iniziare.'}
        </p>
      </div>

      <div className="w-full max-w-md flex flex-col gap-2">
        <div className="relative">
          <input
            type={setupKeyShowRaw ? 'text' : 'password'}
            value={setupKeyInput}
            onChange={e => setSetupKeyInput(e.target.value)}
            onKeyDown={async e => {
              if (e.key !== 'Enter') return;
              if (!GEMINI_KEY_PATTERN.test(setupKeyInput.trim())) return;
              if (setupKeySaving) return;
              await handleSetupSave();
            }}
            placeholder="Incolla qui la tua API Key (AIzaSy... o AQ...)"
            className="app-input font-mono text-sm pr-10"
            style={{
              background: 'var(--bg-input)',
              border: `1px solid ${
                setupKeyInput.trim() && GEMINI_KEY_PATTERN.test(setupKeyInput.trim())
                  ? 'var(--success-ring)'
                  : setupKeyInput.trim()
                    ? 'var(--warning-ring)'
                    : 'var(--border-default)'
              }`,
              color: 'var(--text-primary)',
            }}
          />
          <button
            onClick={() => setSetupKeyShowRaw(v => !v)}
            tabIndex={-1}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 opacity-50 hover:opacity-100 transition-opacity"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: '2px', lineHeight: 1 }}
            aria-label={setupKeyShowRaw ? 'Nascondi chiave' : 'Mostra chiave'}
          >
            {setupKeyShowRaw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        {setupKeyInput.trim() && (
          <p className="text-xs" style={{ color: GEMINI_KEY_PATTERN.test(setupKeyInput.trim()) ? 'var(--success-text)' : 'var(--warning-text)' }}>
            {GEMINI_KEY_PATTERN.test(setupKeyInput.trim()) ? '✓ Formato valido — premi Salva per continuare' : '⚠ Formato non valido — le chiavi iniziano con AIzaSy... o AQ.'}
          </p>
        )}
        <button
          disabled={!GEMINI_KEY_PATTERN.test(setupKeyInput.trim()) || setupKeySaving}
          onClick={handleSetupSave}
          className="premium-button w-full"
          style={!GEMINI_KEY_PATTERN.test(setupKeyInput.trim()) ? { cursor: 'not-allowed', opacity: 0.5 } : {}}
        >
          <Key className="w-4 h-4" />
          {setupKeySaving ? 'Salvataggio…' : 'Salva e inizia'}
        </button>
        {setupKeyError && (
          <p className="text-xs" style={{ color: 'var(--error-text)' }}>❌ {setupKeyError}</p>
        )}
      </div>

      <div className="w-full max-w-md rounded-xl px-5 py-4 flex flex-col gap-2.5" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
        <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-faint)' }}>Come ottenere la chiave in 1 minuto</p>
        <ol className="flex flex-col gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <li className="flex items-start gap-2">
            <span className="shrink-0 w-4 h-4 rounded-full text-[10px] font-bold flex items-center justify-center" style={{ background: 'var(--accent-subtle)', color: 'var(--accent-text, var(--text-secondary))' }}>1</span>
            <span>Vai su <a href="#" onClick={e => { e.preventDefault(); window.pywebview?.api?.open_url?.('https://aistudio.google.com/apikey'); }} className="underline hover:opacity-100 opacity-80" style={{ color: 'var(--accent-text, var(--text-secondary))' }}>aistudio.google.com/apikey</a></span>
          </li>
          <li className="flex items-start gap-2">
            <span className="shrink-0 w-4 h-4 rounded-full text-[10px] font-bold flex items-center justify-center" style={{ background: 'var(--accent-subtle)', color: 'var(--accent-text, var(--text-secondary))' }}>2</span>
            <span>Clicca <strong>"Create API key"</strong> e copia la chiave</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="shrink-0 w-4 h-4 rounded-full text-[10px] font-bold flex items-center justify-center" style={{ background: 'var(--accent-subtle)', color: 'var(--accent-text, var(--text-secondary))' }}>3</span>
            <span>Incollala nel campo qui sopra e premi <strong>Salva e inizia</strong></span>
          </li>
        </ol>
      </div>

      <button onClick={() => setIsSettingsOpen(true)} className="text-xs opacity-60 hover:opacity-100 transition-opacity flex items-center gap-1" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}>
        <Settings className="w-3.5 h-3.5" /> Apri impostazioni avanzate
      </button>
    </div>
  );
}
