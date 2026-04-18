import { useEffect, useState } from 'react';
import { APP_VERSION, GITHUB_API_RELEASES_URL } from '../branding';

const UPDATE_DISMISSED_KEY = 'el-sbobinator.dismissed-update.v1';
const UPDATE_LAST_CHECK_KEY = 'el-sbobinator.last-update-check.v1';
const UPDATE_CHECK_INTERVAL_MS = 15 * 60 * 1000;

export function useUpdateChecker() {
  const [updateAvailable, setUpdateAvailable] = useState<string | null>(null);

  useEffect(() => {
    const compareVersions = (a: string, b: string): number => {
      const parse = (v: string) => v.replace(/^v/, '').split('.').map(p => parseInt(p, 10) || 0);
      const [aMaj, aMin, aPatch] = parse(a);
      const [bMaj, bMin, bPatch] = parse(b);
      return aMaj !== bMaj ? aMaj - bMaj : aMin !== bMin ? aMin - bMin : aPatch - bPatch;
    };

    try {
      const lastCheck = Number(window.localStorage.getItem(UPDATE_LAST_CHECK_KEY) || 0);
      if (Date.now() - lastCheck < UPDATE_CHECK_INTERVAL_MS) return;
    } catch (_) {}

    fetch(GITHUB_API_RELEASES_URL)
      .then(r => r.json())
      .then(data => {
        try { window.localStorage.setItem(UPDATE_LAST_CHECK_KEY, String(Date.now())); } catch (_) {}
        const latest: string = data?.tag_name;
        if (!latest) return;
        try {
          const dismissed = window.localStorage.getItem(UPDATE_DISMISSED_KEY);
          if (dismissed === latest) return;
        } catch (_) {}
        if (compareVersions(latest, APP_VERSION) > 0) {
          setUpdateAvailable(latest);
        }
      })
      .catch(() => {});
  }, []);

  const dismissUpdate = (version: string) => {
    try { window.localStorage.setItem(UPDATE_DISMISSED_KEY, version); } catch (_) {}
    setUpdateAvailable(null);
  };

  return { updateAvailable, dismissUpdate };
}
