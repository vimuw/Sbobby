import { useEffect, useRef, useState } from 'react';

export function useApiReady(appendConsole: (msg: string) => void) {
  const [apiReady, setApiReady] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [fallbackKeys, setFallbackKeys] = useState('');
  const initDoneRef = useRef(false);

  useEffect(() => {
    const onReady = async () => {
      if (initDoneRef.current) return;
      initDoneRef.current = true;
      setApiReady(true);
      appendConsole('Connesso a Python.');
      try {
        const cfg = await window.pywebview?.api?.load_settings?.();
        if (cfg?.api_key) setApiKey(cfg.api_key);
        if (cfg?.fallback_keys?.length) setFallbackKeys(cfg.fallback_keys.join('\n'));
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

  return { apiReady, apiKey, setApiKey, fallbackKeys, setFallbackKeys };
}
