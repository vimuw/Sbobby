import { useEffect, useRef, useState } from 'react';
import type React from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  AudioLines,
  Bot,
  Check,
  CheckCircle,
  FileDown,
  Files,
  Layers,
  Loader,
  Mic,
  Pause,
  Sparkles,
  Timer,
  WifiOff,
  XCircle,
} from 'lucide-react';
import { shortModelName } from '../utils';
import type { AppStatus } from '../appState';

interface ProcessingStatusBannerProps {
  appState: AppStatus;
  currentPhase: string;
  currentModel: string;
  activeProgress: number;
  workDone: { chunks: number; macro: number };
  workTotals: { chunks: number; macro: number };
  currentFileIndex: number;
  currentBatchTotal: number;
  currentFileName?: string;
  startedAt?: number;
}

type PhaseInfo = {
  icon: React.ReactElement;
  iconAnimation: 'spin' | 'pulse' | 'none';
  title: string;
  description: string;
  kind: 'normal' | 'wait' | 'cancel' | 'success';
};

type StepState = 'done' | 'active' | 'pending';
type StepKey = 'preconversione' | 'trascrizione' | 'revisione';
type StepperState = Record<StepKey, StepState> | null;
type WorkKind = 'chunks' | 'macro';

const STEP_TOOLTIPS: Record<StepKey, string> = {
  preconversione: "Normalizza l'audio per renderlo piu' stabile e leggibile nelle fasi successive.",
  trascrizione: 'Il modello analizza i blocchi audio e genera la prima sbobinatura dettagliata.',
  revisione: "Il testo viene ripulito, organizzato e reso piu' chiaro sezione per sezione.",
};

function getPhaseInfo(appState: AppStatus, currentPhase: string): PhaseInfo {
  if (appState === 'canceling') {
    return {
      icon: <XCircle className="w-8 h-8" />,
      iconAnimation: 'none',
      title: 'Interruzione in corso...',
      description: "Attendere il completamento dell'operazione corrente prima di fermarsi.",
      kind: 'cancel',
    };
  }

  const phase = currentPhase.trim();

  if (!phase) {
    return {
      icon: <Loader className="w-8 h-8" />,
      iconAnimation: 'spin',
      title: 'Preparazione...',
      description: "Avvio dell'elaborazione in corso.",
      kind: 'normal',
    };
  }

  if (phase === '__completed__') {
    return {
      icon: <CheckCircle className="w-8 h-8" />,
      iconAnimation: 'none',
      title: 'Sbobinatura completata!',
      description: 'Tutti i passaggi sono stati completati con successo.',
      kind: 'success',
    };
  }

  if (phase.startsWith('Fase 0/3')) {
    return {
      icon: <AudioLines className="w-8 h-8" />,
      iconAnimation: 'pulse',
      title: 'Pre-conversione audio',
      description: "Conversione del file audio in un formato ottimizzato per l'elaborazione.",
      kind: 'normal',
    };
  }

  if (phase.startsWith('Fase 1/3')) {
    return {
      icon: <Mic className="w-8 h-8" />,
      iconAnimation: 'pulse',
      title: 'Trascrizione e sbobinatura',
      description: 'Gemini trascrive e sbobina ogni blocco audio in appunti dettagliati.',
      kind: 'normal',
    };
  }

  if (phase.startsWith('Fase 2/3')) {
    return {
      icon: <Sparkles className="w-8 h-8" />,
      iconAnimation: 'pulse',
      title: 'Revisione e pulizia',
      description: 'Il testo viene rivisto e ripulito da ripetizioni e imprecisioni.',
      kind: 'normal',
    };
  }

  if (phase.startsWith('Fase: esportazione') || phase.startsWith('Fase:esportazione')) {
    return {
      icon: <FileDown className="w-8 h-8" />,
      iconAnimation: 'pulse',
      title: 'Generazione output',
      description: 'Salvataggio del file HTML finale sul Desktop.',
      kind: 'normal',
    };
  }

  if (phase.startsWith('Modello non disponibile')) {
    return {
      icon: <WifiOff className="w-8 h-8" />,
      iconAnimation: 'pulse',
      title: 'In attesa...',
      description: "Il modello AI e' temporaneamente non disponibile. Riprovo automaticamente.",
      kind: 'wait',
    };
  }

  if (phase.startsWith('Rate limit') || phase.includes('Rate limit')) {
    return {
      icon: <Pause className="w-8 h-8" />,
      iconAnimation: 'none',
      title: 'Pausa automatica',
      description: 'Limite richieste API raggiunto. Ripresa automatica tra qualche secondo.',
      kind: 'wait',
    };
  }

  return {
    icon: <Loader className="w-8 h-8" />,
    iconAnimation: 'spin',
    title: 'Elaborazione in corso',
    description: currentPhase,
    kind: 'normal',
  };
}

function getStepperState(currentPhase: string): StepperState {
  const phase = currentPhase.trim();
  if (phase === '__completed__' || phase.startsWith('Fase: esportazione') || phase.startsWith('Fase:esportazione')) {
    return { preconversione: 'done', trascrizione: 'done', revisione: 'done' };
  }
  if (phase.startsWith('Fase 0/3')) {
    return { preconversione: 'active', trascrizione: 'pending', revisione: 'pending' };
  }
  if (phase.startsWith('Fase 1/3')) {
    return { preconversione: 'done', trascrizione: 'active', revisione: 'pending' };
  }
  if (phase.startsWith('Fase 2/3')) {
    return { preconversione: 'done', trascrizione: 'done', revisione: 'active' };
  }
  return null;
}

function parseCurrentIndex(phase: string, stage: WorkKind): { current: number; total: number } | null {
  if (stage === 'chunks') {
    const match = phase.match(/chunk\s+(\d+)\s*\/\s*(\d+)/i);
    if (match) {
      return { current: Number(match[1]), total: Number(match[2]) };
    }
  }

  if (stage === 'macro' && phase.startsWith('Fase 2/3')) {
    const match = phase.match(/\((?:blocco\s+)?(\d+)\s*\/\s*(\d+)\)/i);
    if (match) {
      return { current: Number(match[1]), total: Number(match[2]) };
    }
  }

  return null;
}

function getActiveStepIndex(done: number, total: number): number {
  if (total <= 0) return 0;
  if (done >= total) return total;
  return Math.min(total, Math.max(1, done + 1));
}

function getProgressLabel(
  currentPhase: string,
  workDone: { chunks: number; macro: number },
  workTotals: { chunks: number; macro: number },
): string | null {
  const phase = currentPhase.trim();

  const chunkInfo = parseCurrentIndex(phase, 'chunks');
  if (chunkInfo) return `Blocco ${chunkInfo.current} di ${chunkInfo.total}`;
  if (phase.startsWith('Fase 1/3') && workTotals.chunks > 0) {
    return `Blocco ${getActiveStepIndex(workDone.chunks, workTotals.chunks)} di ${workTotals.chunks}`;
  }

  const macroInfo = parseCurrentIndex(phase, 'macro');
  if (macroInfo) return `Sezione ${macroInfo.current} di ${macroInfo.total}`;
  if (phase.startsWith('Fase 2/3') && workTotals.macro > 0) {
    return `Sezione ${getActiveStepIndex(workDone.macro, workTotals.macro)} di ${workTotals.macro}`;
  }

  return null;
}

function formatElapsed(secs: number): string {
  if (secs < 60) return `Da ${secs}s`;
  const minutes = Math.floor(secs / 60);
  const remainingSeconds = secs % 60;
  if (minutes < 60) return `Da ${minutes}m ${remainingSeconds < 10 ? '0' : ''}${remainingSeconds}s`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `Da ${hours}h ${remainingMinutes}m`;
}

function StepBadge({
  state,
  label,
  num,
  accentColor,
  tooltip,
}: {
  state: StepState;
  label: string;
  num: number;
  accentColor: string;
  tooltip: string;
}) {
  const wrapperStyle: React.CSSProperties = { color: 'var(--text-primary)' };

  const content = state === 'done'
    ? (
        <span className="flex items-center gap-2">
          <span className="flex items-center justify-center w-5 h-5 rounded-full shrink-0" style={{ background: 'var(--success-text)' }}>
            <Check className="w-3 h-3" style={{ color: 'white' }} />
          </span>
          <span className="text-xs line-through" style={{ color: 'var(--text-muted)' }}>{label}</span>
        </span>
      )
    : state === 'active'
      ? (
          <span className="flex items-center gap-2">
            <span className="relative flex items-center justify-center shrink-0">
              <span className="absolute w-5 h-5 rounded-full animate-ping" style={{ background: accentColor, opacity: 0.35 }} />
              <span className="relative flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold" style={{ background: accentColor, color: 'white' }}>
                {num}
              </span>
            </span>
            <span className="text-sm font-semibold" style={{ color: accentColor }}>{label}</span>
          </span>
        )
      : (
          <span className="flex items-center gap-2">
            <span className="flex items-center justify-center w-5 h-5 rounded-full border text-[10px] shrink-0" style={{ borderColor: 'var(--border-default)', color: 'var(--text-muted)' }}>
              {num}
            </span>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</span>
          </span>
        );

  return (
    <span
      className="group relative inline-flex focus:outline-none"
      style={wrapperStyle}
      tabIndex={0}
      aria-label={`${label}. ${tooltip}`}
    >
      <span className="cursor-help">{content}</span>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-20 mt-2 w-48 -translate-x-1/2 translate-y-1 rounded-xl border px-3 py-2 text-left text-[11px] leading-snug opacity-0 shadow-xl transition-all duration-150 group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:translate-y-0 group-focus-within:opacity-100"
        style={{
          background: 'var(--bg-elevated)',
          borderColor: 'var(--border-default)',
          color: 'var(--text-secondary)',
        }}
      >
        {tooltip}
      </span>
    </span>
  );
}

export function ProcessingStatusBanner({
  appState,
  currentPhase,
  currentModel,
  activeProgress,
  workDone,
  workTotals,
  currentFileIndex,
  currentBatchTotal,
  currentFileName,
  startedAt,
}: ProcessingStatusBannerProps) {
  const { icon, iconAnimation, title, description, kind } = getPhaseInfo(appState, currentPhase);
  const isCanceling = appState === 'canceling';
  const isWaiting = kind === 'wait';

  const lastNormalPhaseRef = useRef('');
  if (kind === 'normal') lastNormalPhaseRef.current = currentPhase;
  const phaseForMeta = isWaiting ? lastNormalPhaseRef.current : currentPhase;

  const stepperState = getStepperState(phaseForMeta);
  const progressLabel = getProgressLabel(phaseForMeta, workDone, workTotals);

  const [elapsedSecs, setElapsedSecs] = useState(0);

  useEffect(() => {
    if (!startedAt) return;
    const update = () => setElapsedSecs(Math.floor((Date.now() - startedAt) / 1000));
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  const accentColor = isCanceling
    ? 'var(--error-text)'
    : kind === 'wait'
      ? 'var(--error-text)'
      : kind === 'success'
        ? 'var(--success-text)'
        : 'var(--processing-text)';

  const accentSubtle = isCanceling
    ? 'var(--error-subtle)'
    : kind === 'wait'
      ? 'var(--error-subtle)'
      : kind === 'success'
        ? 'var(--success-subtle)'
        : 'var(--processing-bg)';

  const progressFill = isCanceling
    ? 'linear-gradient(90deg, var(--error-bg), var(--error-text))'
    : kind === 'wait'
      ? 'linear-gradient(90deg, var(--error-bg), var(--error-text))'
      : kind === 'success'
        ? 'linear-gradient(90deg, var(--success-subtle), var(--success-text))'
        : 'linear-gradient(90deg, var(--accent-gradient-start), var(--accent-gradient-end))';

  const isDimmed = isCanceling || isWaiting;

  const metaChips: Array<{ icon: React.ReactElement; label: string }> = [];
  if (currentModel && kind !== 'success') {
    metaChips.push({ icon: <Bot className="w-3 h-3" />, label: shortModelName(currentModel) });
  }
  if (progressLabel) {
    metaChips.push({ icon: <Layers className="w-3 h-3" />, label: progressLabel });
  }
  if (currentBatchTotal > 1) {
    metaChips.push({ icon: <Files className="w-3 h-3" />, label: `File ${currentFileIndex + 1} di ${currentBatchTotal}` });
  }
  if (startedAt && elapsedSecs > 0 && kind !== 'success') {
    metaChips.push({ icon: <Timer className="w-3 h-3" />, label: formatElapsed(elapsedSecs) });
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8, transition: { duration: 0.18, ease: 'easeIn' } }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
      className="relative w-full px-5 py-6 sm:px-7 sm:py-7"
      aria-label="Stato elaborazione"
    >

      <div
        className="absolute left-1/2 top-0 h-28 w-28 -translate-x-1/2 rounded-full blur-3xl"
        style={{ background: accentSubtle, opacity: 0.45 }}
      />

      <div className="relative z-10 flex flex-col items-center gap-5 text-center">
        <AnimatePresence mode="wait">
          <motion.div
            key={title}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="relative flex items-center justify-center"
          >
            {iconAnimation === 'pulse' && (
              <span
                className="absolute inset-0 rounded-full animate-ping"
                style={{ background: accentSubtle, opacity: 0.6 }}
              />
            )}
            <div
              className="relative flex h-16 w-16 items-center justify-center rounded-full"
              style={{ background: accentSubtle, color: accentColor }}
            >
              <div className={iconAnimation === 'spin' ? 'animate-spin' : iconAnimation === 'pulse' ? 'animate-pulse' : ''}>
                {icon}
              </div>
            </div>
          </motion.div>
        </AnimatePresence>

        <AnimatePresence mode="wait">
          <motion.div
            key={`${title}-${description}`}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="flex max-w-xl flex-col items-center gap-1.5"
          >
            <h2 className="text-2xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
              {title}
            </h2>
            <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              {description}
            </p>
          </motion.div>
        </AnimatePresence>

        <div className="flex flex-col items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.24em]" style={{ color: 'var(--text-muted)' }}>
            Avanzamento
          </span>
          <span className="text-5xl font-bold leading-none tabular-nums" style={{ color: accentColor }}>
            {activeProgress}%
          </span>
        </div>

        <div className="w-full max-w-2xl">
          <div className="h-3 w-full overflow-hidden rounded-full" style={{ background: 'var(--progress-bg)' }}>
            <motion.div
              className="processing-progress-fill h-full rounded-full"
              style={{ background: progressFill }}
              initial={{ width: 0 }}
              animate={{ width: `${activeProgress}%` }}
              transition={{ ease: 'linear', duration: 0.3 }}
            />
          </div>
        </div>

        {currentFileName && (
          <p className="max-w-xl truncate text-sm font-medium" style={{ color: 'var(--text-primary)' }} title={currentFileName}>
            {currentFileName}
          </p>
        )}

        {(metaChips.length > 0 || stepperState) && (
          <div
            className="flex flex-col items-center gap-3"
            style={isDimmed ? { opacity: 0.45, filter: 'grayscale(0.6)', transition: 'opacity 0.3s, filter 0.3s' } : undefined}
          >
            {metaChips.length > 0 && (
              <div className="flex flex-wrap items-center justify-center gap-2">
                {metaChips.map(({ icon, label }, index) => (
                  <span
                    key={`${label}-${index}`}
                    className="flex items-center gap-1 rounded-full px-2.5 py-1 text-xs"
                    style={{ background: 'var(--progress-bg)', color: 'var(--text-secondary)' }}
                  >
                    {icon}
                    {label}
                  </span>
                ))}
              </div>
            )}
            {stepperState && (
              <div className="flex flex-wrap items-center justify-center gap-3 pt-1">
                <StepBadge state={stepperState.preconversione} label="Pre-conversione" num={1} accentColor={isDimmed ? 'var(--text-muted)' : accentColor} tooltip={STEP_TOOLTIPS.preconversione} />
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--border-default)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-hidden="true"><polyline points="9 18 15 12 9 6" /></svg>
                <StepBadge state={stepperState.trascrizione} label="Trascrizione" num={2} accentColor={isDimmed ? 'var(--text-muted)' : accentColor} tooltip={STEP_TOOLTIPS.trascrizione} />
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--border-default)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-hidden="true"><polyline points="9 18 15 12 9 6" /></svg>
                <StepBadge state={stepperState.revisione} label="Revisione" num={3} accentColor={isDimmed ? 'var(--text-muted)' : accentColor} tooltip={STEP_TOOLTIPS.revisione} />
              </div>
            )}
          </div>
        )}
      </div>
    </motion.section>
  );
}
