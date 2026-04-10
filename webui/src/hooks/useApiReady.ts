import { useEffect, useRef, useState } from 'react';
import type { ModelOption } from '../bridge';

export function useApiReady(appendConsole: (msg: string) => void) {
  const [apiReady, setApiReady] = useState(false);
  const [bridgeDelayed, setBridgeDelayed] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [fallbackKeys, setFallbackKeys] = useState<string[]>([]);
  const [preferredModel, setPreferredModel] = useState('gemini-2.5-flash');
  const [fallbackModels, setFallbackModels] = useState<string[]>([]);
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const initDoneRef = useRef(false);
  const inFlightRef = useRef(false);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const appendConsoleRef = useRef(appendConsole);

  useEffect(() => {
    appendConsoleRef.current = appendConsole;
  }, [appendConsole]);

  useEffect(() => {
    let alive = true;

    const tryBootstrap = async () => {
      if (initDoneRef.current) return;
      if (inFlightRef.current) return;
      if (!window.pywebview?.api?.load_settings) return;

      inFlightRef.current = true;
      try {
        const cfg = await window.pywebview.api.load_settings();
        if (!alive) return;
        initDoneRef.current = true;
        setBridgeDelayed(false);
        setApiReady(true);
        appendConsoleRef.current('Connesso a Python.');
        if (cfg?.api_key) setApiKey(cfg.api_key);
        if (cfg?.fallback_keys?.length) setFallbackKeys(cfg.fallback_keys);
        if (cfg?.preferred_model) setPreferredModel(cfg.preferred_model);
        if (cfg?.fallback_models?.length) setFallbackModels(cfg.fallback_models);
        if (cfg?.available_models?.length) setAvailableModels(cfg.available_models);
      } catch (e) {
        console.error('Load settings failed:', e);
        if (!alive) return;
        if (!initDoneRef.current && retriesRef.current < 3) {
          retriesRef.current += 1;
          if (retryTimerRef.current !== null) clearTimeout(retryTimerRef.current);
          retryTimerRef.current = setTimeout(tryBootstrap, 2000);
        } else if (!initDoneRef.current) {
          setBridgeDelayed(true);
        }
      } finally {
        inFlightRef.current = false;
      }
    };

    const onBridgeReady = () => {
      if (!initDoneRef.current) {
        if (retryTimerRef.current !== null) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null; }
        retriesRef.current = 0;
      }
      tryBootstrap();
    };
    window.addEventListener('pywebviewready', onBridgeReady);
    tryBootstrap();

    const delayedWarning = setTimeout(() => {
      if (initDoneRef.current) return;
      if (retryTimerRef.current !== null) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null; }
      retriesRef.current = 3;
      setBridgeDelayed(true);
      if (inFlightRef.current) return;
      tryBootstrap();
    }, 5000);

    return () => {
      alive = false;
      window.removeEventListener('pywebviewready', onBridgeReady);
      clearTimeout(delayedWarning);
      if (retryTimerRef.current !== null) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null; }
    };
  }, []);

  return {
    apiReady,
    bridgeDelayed,
    apiKey,
    setApiKey,
    fallbackKeys,
    setFallbackKeys,
    preferredModel,
    setPreferredModel,
    fallbackModels,
    setFallbackModels,
    availableModels,
  };
}
