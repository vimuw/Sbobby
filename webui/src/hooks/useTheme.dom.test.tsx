import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useTheme } from './useTheme';

const THEME_KEY = 'el-sbobinator.theme.v1';

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

afterEach(() => {
  localStorage.clear();
});

describe('useTheme', () => {
  it('defaults to dark mode', () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.themeMode).toBe('dark');
  });

  it('restores persisted light theme from localStorage', async () => {
    localStorage.setItem(THEME_KEY, 'light');
    const { result } = renderHook(() => useTheme());
    await act(async () => {});
    expect(result.current.themeMode).toBe('light');
  });

  it('restores persisted dark theme from localStorage', async () => {
    localStorage.setItem(THEME_KEY, 'dark');
    const { result } = renderHook(() => useTheme());
    await act(async () => {});
    expect(result.current.themeMode).toBe('dark');
  });

  it('persists theme change to localStorage', async () => {
    const { result } = renderHook(() => useTheme());
    await act(async () => {
      result.current.setThemeMode('light');
    });
    expect(localStorage.getItem(THEME_KEY)).toBe('light');
  });

  it('sets data-theme on documentElement', async () => {
    const { result } = renderHook(() => useTheme());
    await act(async () => {
      result.current.setThemeMode('light');
    });
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('setThemeMode toggles between light and dark', async () => {
    const { result } = renderHook(() => useTheme());
    await act(async () => { result.current.setThemeMode('light'); });
    expect(result.current.themeMode).toBe('light');
    await act(async () => { result.current.setThemeMode('dark'); });
    expect(result.current.themeMode).toBe('dark');
  });
});
