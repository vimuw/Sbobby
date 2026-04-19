import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useConsole } from './useConsole';

describe('useConsole', () => {
  it('initializes with a startup log entry', () => {
    const { result } = renderHook(() => useConsole());
    expect(result.current.consoleLogs.length).toBe(1);
    expect(result.current.consoleLogs[0]).toContain('El Sbobinator avviato');
  });

  it('appendConsole adds a new log entry', async () => {
    const { result } = renderHook(() => useConsole());
    await act(async () => {
      result.current.appendConsole('Test message');
      await new Promise(r => requestAnimationFrame(r));
    });
    const found = result.current.consoleLogs.some(l => l.includes('Test message'));
    expect(found).toBe(true);
  });

  it('appendConsole batches multiple messages in one rAF', async () => {
    const { result } = renderHook(() => useConsole());
    await act(async () => {
      result.current.appendConsole('msg A');
      result.current.appendConsole('msg B');
      await new Promise(r => requestAnimationFrame(r));
    });
    expect(result.current.consoleLogs.some(l => l.includes('msg A'))).toBe(true);
    expect(result.current.consoleLogs.some(l => l.includes('msg B'))).toBe(true);
  });

  it('caps logs at 300 entries', async () => {
    const { result } = renderHook(() => useConsole());
    await act(async () => {
      for (let i = 0; i < 350; i++) {
        result.current.appendConsole(`msg ${i}`);
      }
      await new Promise(r => requestAnimationFrame(r));
    });
    expect(result.current.consoleLogs.length).toBeLessThanOrEqual(300);
  });
});
