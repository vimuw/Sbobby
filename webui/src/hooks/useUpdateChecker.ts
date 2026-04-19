import { useCallback, useEffect, useRef, useState } from 'react';
import { APP_VERSION, GITHUB_API_RELEASES_URL } from '../branding';

const UPDATE_DISMISSED_KEY = 'el-sbobinator.dismissed-update.v1';
const UPDATE_LAST_CHECK_KEY = 'el-sbobinator.last-update-check.v1';
const UPDATE_CHECK_INTERVAL_MS = 15 * 60 * 1000;

const compareVersions = (a: string, b: string): number => {
  const parse = (v: string) => v.replace(/^v/, '').split('.').map(p => parseInt(p, 10) || 0);
  const [aMaj, aMin, aPatch] = parse(a);
  const [bMaj, bMin, bPatch] = parse(b);
  return aMaj !== bMaj ? aMaj - bMaj : aMin !== bMin ? aMin - bMin : aPatch - bPatch;
};

export function useUpdateChecker() {
  const [updateAvailable, setUpdateAvailable] = useState<string | null>(null);
  const [latestVersion, setLatestVersion] = useState<string | null>(null);
  const [isCheckingUpdate, setIsCheckingUpdate] = useState(false);
  const [hasChecked, setHasChecked] = useState(false);
  const isCheckingRef = useRef(false);

  const checkForUpdates = useCallback((force: boolean = false) => {
    if (isCheckingRef.current) return;
    if (!force) {
      try {
        const lastCheck = Number(window.localStorage.getItem(UPDATE_LAST_CHECK_KEY) || 0);
        if (Date.now() - lastCheck < UPDATE_CHECK_INTERVAL_MS) return;
      } catch (_) {}
    }
    isCheckingRef.current = true;
    if (force) setIsCheckingUpdate(true);
    fetch(GITHUB_API_RELEASES_URL)
      .then(r => r.json())
      .then(data => {
        try { window.localStorage.setItem(UPDATE_LAST_CHECK_KEY, String(Date.now())); } catch (_) {}
        const latest: string = data?.tag_name;
        if (!latest) return;
        if (compareVersions(latest, APP_VERSION) > 0) {
          setLatestVersion(latest);
          try {
            const dismissed = window.localStorage.getItem(UPDATE_DISMISSED_KEY);
            if (dismissed !== latest) setUpdateAvailable(latest);
          } catch (_) {
            setUpdateAvailable(latest);
          }
        }
      })
      .catch(() => {})
      .finally(() => {
        isCheckingRef.current = false;
        if (force) setIsCheckingUpdate(false);
        setHasChecked(true);
      });
  }, []);

  useEffect(() => {
    checkForUpdates(false);
  }, [checkForUpdates]);

  const dismissUpdate = (version: string) => {
    try { window.localStorage.setItem(UPDATE_DISMISSED_KEY, version); } catch (_) {}
    setUpdateAvailable(null);
  };

  return { updateAvailable, latestVersion, isCheckingUpdate, hasChecked, checkForUpdates, dismissUpdate };
}
