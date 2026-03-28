import { useEffect, useState } from 'react';

export function useApiReady(appendConsole: (msg: string) => void) {
  const [apiReady, setApiReady] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [fallbackKeys, setFallbackKeys] = useState('');

  useEffect(() => {
    const onReady = async () => {
      if (apiReady) return;
      setApiReady(true);
      appendConsole('Connesso a Python.');
      try {
        const cfg = await window.pywebview.api?.load_settings?.();
        if (cfg?.api_key) setApiKey(cfg.api_key);
        if (cfg?.fallback_keys?.length) setFallbackKeys(cfg.fallback_keys.join('\n'));
      } catch (e) { console.error('Load settings failed:', e); }
    };

    window.addEventListener('pywebviewready', onReady);
    if (window.pywebview?.api) onReady();

    const warmup = setTimeout(async () => {
      try { if (window.pywebview?.api) await window.pywebview.api.load_settings(); } catch (_) {}
    }, 100);

    const fallback = setTimeout(() => {
      if (!window.pywebview?.api) {
        console.warn('pywebview bridge not available after 5s fallback.');
      }
      setApiReady(true);
    }, 5000);

    return () => {
      window.removeEventListener('pywebviewready', onReady);
      clearTimeout(warmup);
      clearTimeout(fallback);
    };
  }, [apiReady, appendConsole]);

  return { apiReady, apiKey, setApiKey, fallbackKeys, setFallbackKeys };
}
