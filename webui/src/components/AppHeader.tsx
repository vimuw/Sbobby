import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { AlertTriangle, Loader2, Moon, Settings, Sun, Terminal, X, Zap } from 'lucide-react';
import type { AppStatus } from '../appState';
import { GITHUB_RELEASES_URL } from '../branding';

const CONFETTI_COLORS = ['#FF6B6B', '#FFD93D', '#6BCB77', '#4D96FF', '#FF922B', '#CC5DE8', '#FF8FAB'];
type ConfettiParticle = { id: number; color: string; angle: number; distance: number; size: number; round: boolean };

interface AppHeaderProps {
  apiReady: boolean;
  bridgeDelayed: boolean;
  hasApiKey: boolean;
  isApiKeyValid: boolean;
  appState: AppStatus;
  themeMode: 'light' | 'dark';
  setThemeMode: Dispatch<SetStateAction<'light' | 'dark'>>;
  showConsole: boolean;
  setShowConsole: (v: boolean) => void;
  setIsSettingsOpen: (v: boolean) => void;
  updateAvailable: string | null;
  dismissUpdate: (version: string) => void;
}

export function AppHeader({
  apiReady, bridgeDelayed, hasApiKey, isApiKeyValid, appState,
  themeMode, setThemeMode, showConsole, setShowConsole, setIsSettingsOpen,
  updateAvailable, dismissUpdate,
}: AppHeaderProps) {
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [isPeakHour, setIsPeakHour] = useState(() => { const h = new Date().getHours(); return h >= 15 && h < 20; });
  const [isPeakDismissed, setIsPeakDismissed] = useState(() => {
    const ts = localStorage.getItem('peakBannerDismissedUntil');
    return ts ? Date.now() < Number(ts) : false;
  });
  const [confettiParticles, setConfettiParticles] = useState<ConfettiParticle[]>([]);
  const confettiIdRef = useRef(0);
  const lastConfettiRef = useRef(0);

  useEffect(() => {
    const check = () => {
      const h = new Date().getHours();
      setIsPeakHour(h >= 15 && h < 20);
    };
    const id = setInterval(check, 60_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (isPeakHour) {
      const ts = localStorage.getItem('peakBannerDismissedUntil');
      setIsPeakDismissed(ts ? Date.now() < Number(ts) : false);
    }
  }, [isPeakHour]);

  const fireConfetti = useCallback(() => {
    const now = Date.now();
    if (now - lastConfettiRef.current < 350) return;
    lastConfettiRef.current = now;
    const particles: ConfettiParticle[] = Array.from({ length: 14 }, () => ({
      id: confettiIdRef.current++,
      color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
      angle: Math.random() * 360,
      distance: 28 + Math.random() * 34,
      size: 3 + Math.floor(Math.random() * 4),
      round: Math.random() > 0.45,
    }));
    setConfettiParticles(prev => [...prev, ...particles]);
    setTimeout(() => {
      setConfettiParticles(prev => prev.filter(p => !particles.some(pp => pp.id === p.id)));
    }, 850);
  }, []);

  const titleGradient = { background: 'linear-gradient(90deg, var(--gradient-title-from), var(--gradient-title-to))', WebkitBackgroundClip: 'text' as const, WebkitTextFillColor: 'transparent' };

  return (
    <>
      <header className="sticky top-0 z-40 backdrop-blur-2xl" style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--header-bg)' }}>
        <div className="max-w-3xl mx-auto px-5 sm:px-6 min-h-[84px] flex items-center justify-between gap-4">
          <div className="flex items-center gap-1">
            <div style={{ position: 'relative', display: 'inline-block' }} onMouseEnter={fireConfetti}>
              <img src="./icon.png" alt="El Sbobinator" className="app-logo" draggable={false} />
              {confettiParticles.map(p => {
                const rad = (p.angle * Math.PI) / 180;
                const tx = Math.cos(rad) * p.distance;
                const ty = Math.sin(rad) * p.distance - 8;
                return (
                  <motion.span
                    key={p.id}
                    initial={{ x: 0, y: 0, opacity: 1, scale: 1 }}
                    animate={{ x: tx, y: ty, opacity: 0, scale: 0.4 }}
                    transition={{ duration: 0.7, ease: 'easeOut' }}
                    style={{
                      position: 'absolute',
                      top: '50%',
                      left: '50%',
                      marginLeft: -p.size / 2,
                      marginTop: -p.size / 2,
                      width: p.size,
                      height: p.size,
                      borderRadius: p.round ? '50%' : '2px',
                      background: p.color,
                      pointerEvents: 'none',
                      zIndex: 50,
                    }}
                  />
                );
              })}
            </div>
            <h1 className="brand-mark text-[1.45rem] sm:text-[1.75rem] font-semibold flex items-baseline tracking-tight leading-none overflow-visible py-1">
              <span style={titleGradient}>El&nbsp;</span>
              <span className="relative inline-block mx-[2px] overflow-visible">
                <svg className="absolute -top-[10px] left-1/2 -translate-x-[42%] w-[22px] h-[32px] drop-shadow-md z-10 pointer-events-none" viewBox="0 0 32 50" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ transform: 'rotate(-10deg)' }}>
                  <path d="M 3 22 C 5 40, 12 48, 17 48 C 23 48, 28 38, 29 22" fill="none" stroke="#D19A3F" strokeWidth="1.5" strokeLinecap="round" />
                  <circle cx="17" cy="48" r="2" fill="#D96D42" />
                  <circle cx="17" cy="48" r="1" fill="#F5D57F" />
                  <path d="M 2 22 C 2 18, 30 18, 30 22" fill="#C38243"/>
                  <path d="M 9 18 C 9 18, 11 4, 16 4 C 21 4, 23 18, 23 18 Z" fill="#F2C86F"/>
                  <path d="M 9.5 15 Q 16 17 22.5 15 L 23 18 Q 16 20 9.5 15 Z" fill="#D96D42"/>
                  <path d="M 10 12 Q 16 14 22 12 L 22.5 15 Q 16 17 10 15 Z" fill="#2B9B7D"/>
                  <path d="M 10.5 9 Q 16 11 21.5 9 L 22 12 Q 16 14 10.5 12 Z" fill="#FFF5E4"/>
                  <path d="M 2 22 C 2 28, 30 28, 30 22 C 30 20, 25 18, 16 18 C 7 18, 2 20, 2 22 Z" fill="#F2C86F"/>
                  <path d="M 2 22 C 2 28, 30 28, 30 22" fill="none" stroke="#C38243" strokeWidth="1.5"/>
                </svg>
                <span className="relative z-0" style={titleGradient}>S</span>
              </span>
              <span style={titleGradient}>bobinator</span>
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="premium-badge" style={{
              color: !apiReady ? (bridgeDelayed ? 'var(--error-text)' : 'var(--warning-text)') : !hasApiKey ? 'var(--text-secondary)' : !isApiKeyValid ? 'var(--warning-text)' : 'var(--success-text)',
              borderColor: !apiReady ? (bridgeDelayed ? 'var(--error-ring)' : 'var(--warning-ring)') : !hasApiKey ? 'var(--border-default)' : !isApiKeyValid ? 'var(--warning-ring)' : 'var(--success-ring)',
              background: !apiReady ? (bridgeDelayed ? 'var(--error-subtle)' : 'var(--warning-subtle)') : !hasApiKey ? 'rgba(255,255,255,0.02)' : !isApiKeyValid ? 'var(--warning-subtle)' : 'var(--success-subtle)',
            }}>
              <span className={`inline-flex h-2.5 w-2.5 rounded-full ${appState === 'processing' ? 'animate-pulse' : ''}`} style={{ background: !apiReady ? (bridgeDelayed ? 'var(--error-bg)' : 'var(--warning-bg)') : !hasApiKey ? 'var(--text-faint)' : !isApiKeyValid ? 'var(--warning-bg)' : 'var(--success-bg)' }} />
              {!apiReady ? (bridgeDelayed ? 'Bridge in ritardo' : 'Bridge in avvio') : !hasApiKey ? 'Configura API' : !isApiKeyValid ? 'Chiave non valida' : 'API pronta'}
            </span>
            <button
              onClick={() => setThemeMode(prev => prev === 'dark' ? 'light' : 'dark')}
              className="icon-button icon-btn-theme"
              aria-label={themeMode === 'dark' ? 'Attiva tema chiaro' : 'Attiva tema scuro'}
              title={themeMode === 'dark' ? 'Tema chiaro' : 'Tema scuro'}
            >
              {themeMode === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>
            <button
              onClick={() => {
                const next = !showConsole;
                setShowConsole(next);
                localStorage.setItem('show_console', String(next));
              }}
              className={`icon-button icon-btn-console${showConsole ? ' icon-button--active' : ''}`}
              title={showConsole ? 'Nascondi console' : 'Mostra console'}
              aria-label={showConsole ? 'Nascondi console' : 'Mostra console'}
            >
              <Terminal className="w-5 h-5" />
            </button>
            <button onClick={() => setIsSettingsOpen(true)} className="icon-button icon-btn-settings" aria-label="Apri impostazioni">
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>
        <AnimatePresence>
          {isPeakHour && !isPeakDismissed && (
            <motion.div
              key="peak-hour-banner"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              className="w-full overflow-hidden"
              style={{ borderTop: '1px solid var(--warning-ring, var(--border-default))', background: 'var(--warning-subtle)' }}
            >
              <div className="max-w-6xl mx-auto px-5 sm:px-6 py-2.5 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2.5 text-sm font-medium" style={{ color: 'var(--warning-text)' }}>
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>Fascia oraria di punta (15:00–20:00): tutti i modelli Gemini Flash possono subire <strong>rallentamenti o errori 503</strong> per traffico elevato sui server Google. Gemini 3 Flash è il più colpito; Gemini 2.5 Flash è generalmente più stabile, ma non immune da problemi.</span>
                </div>
                <button
                  onClick={() => { localStorage.setItem('peakBannerDismissedUntil', String(Date.now() + 3_600_000)); setIsPeakDismissed(true); }}
                  className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--warning-text)', padding: '2px', lineHeight: 1 }}
                  aria-label="Chiudi avviso fascia oraria"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </header>
      <AnimatePresence>
        {updateAvailable && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="w-full"
            style={{ background: 'var(--accent-subtle)', borderBottom: '1px solid var(--accent-ring, var(--border-default))' }}
          >
            <div className="max-w-6xl mx-auto px-5 sm:px-6 py-2.5 flex flex-col gap-1">
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-2.5 text-sm font-medium" style={{ color: 'var(--accent-text, var(--text-primary))' }}>
                  <Zap className="w-4 h-4 shrink-0" />
                  <span>Nuova versione disponibile: <strong>{updateAvailable}</strong></span>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <button
                    disabled={isUpdating}
                    onClick={async () => {
                      if (isUpdating) return;
                      setIsUpdating(true);
                      setUpdateError(null);
                      try {
                        const result = await window.pywebview?.api?.download_and_install_update?.(updateAvailable!);
                        if (!result?.ok) {
                          setUpdateError(result?.error ?? 'Download fallito');
                          setIsUpdating(false);
                          window.pywebview?.api?.open_url?.(GITHUB_RELEASES_URL);
                        } else {
                          setTimeout(() => setIsUpdating(false), 3000);
                        }
                      } catch (e) {
                        setUpdateError(String(e));
                        setIsUpdating(false);
                        window.pywebview?.api?.open_url?.(GITHUB_RELEASES_URL);
                      }
                    }}
                    className="flex items-center gap-1.5 text-xs"
                    style={{ background: 'none', border: 'none', padding: 0, cursor: isUpdating ? 'default' : 'pointer', textDecoration: 'underline', color: 'var(--accent-text, var(--text-primary))', opacity: isUpdating ? 0.5 : 1 }}
                  >
                    {isUpdating
                      ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Download in corso…</>
                      : 'Installa aggiornamento'}
                  </button>
                  <button
                    onClick={() => dismissUpdate(updateAvailable)}
                    aria-label="Chiudi avviso aggiornamento"
                    className="text-xs"
                    style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textDecoration: 'underline', color: 'var(--text-muted)' }}
                  >
                    Ignora
                  </button>
                </div>
              </div>
              {updateError && (
                <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--color-error, #ef4444)' }}>
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  <span>{updateError} — si è aperta la pagina GitHub per scaricare manualmente.</span>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
