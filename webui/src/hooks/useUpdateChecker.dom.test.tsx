import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useUpdateChecker } from './useUpdateChecker';

const LAST_CHECK_KEY = 'el-sbobinator.last-update-check.v1';
const DISMISSED_KEY = 'el-sbobinator.dismissed-update.v1';

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe('useUpdateChecker', () => {
  it('starts with no update available', () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ tag_name: null })));
    const { result } = renderHook(() => useUpdateChecker());
    expect(result.current.updateAvailable).toBeNull();
  });

  it('detects a newer version', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ tag_name: 'v99.0.0' })));
    const { result } = renderHook(() => useUpdateChecker());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.updateAvailable).toBe('v99.0.0');
  });

  it('does not show update for same version', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ tag_name: 'v0.0.0' })));
    const { result } = renderHook(() => useUpdateChecker());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.updateAvailable).toBeNull();
  });

  it('dismissUpdate clears updateAvailable and saves to localStorage', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ tag_name: 'v99.0.0' })));
    const { result } = renderHook(() => useUpdateChecker());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      result.current.dismissUpdate('v99.0.0');
    });
    expect(result.current.updateAvailable).toBeNull();
    expect(localStorage.getItem(DISMISSED_KEY)).toBe('v99.0.0');
  });

  it('skips fetch if already checked recently', async () => {
    localStorage.setItem(LAST_CHECK_KEY, String(Date.now()));
    renderHook(() => useUpdateChecker());
    await act(async () => { await Promise.resolve(); });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('does not show update if version equals dismissed version', async () => {
    localStorage.setItem(DISMISSED_KEY, 'v99.0.0');
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ tag_name: 'v99.0.0' })));
    const { result } = renderHook(() => useUpdateChecker());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.updateAvailable).toBeNull();
  });

  it('handles fetch error gracefully', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('network error'));
    const { result } = renderHook(() => useUpdateChecker());
    await act(async () => { await Promise.resolve(); });
    expect(result.current.updateAvailable).toBeNull();
  });
});
