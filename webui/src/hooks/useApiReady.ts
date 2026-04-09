import { useEffect, useRef, useState } from 'react';
import type { ModelOption } from '../bridge';

export function useApiReady(appendConsole: (msg: string) => void) {
  const [apiReady, setApiReady] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [fallbackKeys, setFallbackKeys] = useState<string[]>([]);
  const [preferredModel, setPreferredModel] = useState('gemini-3-flash-preview');
  const [fallbackModels, setFallbackModels] = useState<string[]>([]);
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const initDoneRef = useRef(false);
  const appendConsoleRef = useRef(appendConsole);

  useEffect(() => {
    appendConsoleRef.current = appendConsole;
  }, [appendConsole]);

  useEffect(() => {
    const onReady = async () => {
      if (initDoneRef.current) return;
      initDoneRef.current = true;
      setApiReady(true);
      appendConsoleRef.current('Connesso a Python.');
      try {
        const cfg = await window.pywebview?.api?.load_settings?.();
        if (cfg?.api_key) setApiKey(cfg.api_key);
        if (cfg?.fallback_keys?.length) setFallbackKeys(cfg.fallback_keys);
        if (cfg?.preferred_model) setPreferredModel(cfg.preferred_model);
        if (cfg?.fallback_models?.length) setFallbackModels(cfg.fallback_models);
        if (cfg?.available_models?.length) setAvailableModels(cfg.available_models);
      } catch (e) { console.error('Load settings failed:', e); }
    };

    window.addEventListener('pywebviewready', onReady);
    if (window.pywebview?.api) onReady();

    const fallback = setTimeout(onReady, 5000);

    return () => {
      window.removeEventListener('pywebviewready', onReady);
      clearTimeout(fallback);
    };
  }, []);

  return {
    apiReady,
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
