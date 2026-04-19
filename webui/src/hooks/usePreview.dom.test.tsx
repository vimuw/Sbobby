import { renderHook, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { usePreview } from './usePreview';
import type { Dispatch } from 'react';
import type { ProcessingAction } from '../appState';
import type { ArchiveSession } from '../bridge';

function setPywebview(api: Record<string, unknown> | undefined) {
  Object.defineProperty(window, 'pywebview', {
    value: api === undefined ? undefined : { api },
    writable: true,
    configurable: true,
  });
}

function makeOptions(overrides: Partial<{
  appendConsole: (msg: string) => void;
  dispatch: Dispatch<ProcessingAction>;
  setArchiveSessions: Dispatch<React.SetStateAction<ArchiveSession[]>>;
}> = {}) {
  return {
    appendConsole: vi.fn(),
    dispatch: vi.fn() as unknown as Dispatch<ProcessingAction>,
    setArchiveSessions: vi.fn() as unknown as Dispatch<React.SetStateAction<ArchiveSession[]>>,
    ...overrides,
  };
}

beforeEach(() => {
  localStorage.clear();
  setPywebview(undefined);
});
afterEach(() => {
  localStorage.clear();
  setPywebview(undefined);
});

describe('usePreview', () => {
  it('initialises with content null', () => {
    const { result } = renderHook(() => usePreview(makeOptions()));
    expect(result.current.preview.content).toBeNull();
  });

  it('openPreview logs error when bridge is unavailable', async () => {
    const appendConsole = vi.fn();
    const { result } = renderHook(() => usePreview(makeOptions({ appendConsole })));
    await act(async () => {
      await result.current.openPreview('/file.html', 'test', undefined, undefined, undefined);
    });
    expect(appendConsole).toHaveBeenCalledWith(expect.stringContaining('non disponibile'));
  });

  it('openPreview loads content when bridge succeeds', async () => {
    const appendConsole = vi.fn();
    setPywebview({
      read_html_content: vi.fn().mockResolvedValue({ ok: true, content: '<body><p>hello</p></body>' }),
      stream_media_file: vi.fn().mockResolvedValue({ ok: false }),
    });
    const { result } = renderHook(() => usePreview(makeOptions({ appendConsole })));
    await act(async () => {
      await result.current.openPreview('/file.html', 'My File', '/audio.mp3', 'f1', '/session');
    });
    expect(result.current.preview.content).not.toBeNull();
    expect(result.current.preview.title).toBe('My File');
    expect(result.current.preview.path).toBe('/file.html');
  });

  it('openPreview logs error when bridge returns !ok', async () => {
    const appendConsole = vi.fn();
    setPywebview({
      read_html_content: vi.fn().mockResolvedValue({ ok: false, error: 'file not found' }),
    });
    const { result } = renderHook(() => usePreview(makeOptions({ appendConsole })));
    await act(async () => {
      await result.current.openPreview('/file.html', 'test');
    });
    expect(appendConsole).toHaveBeenCalledWith(expect.stringContaining('file not found'));
  });

  it('openPreview logs error on thrown exception', async () => {
    const appendConsole = vi.fn();
    setPywebview({
      read_html_content: vi.fn().mockRejectedValue(new Error('network failure')),
    });
    const { result } = renderHook(() => usePreview(makeOptions({ appendConsole })));
    await act(async () => {
      await result.current.openPreview('/file.html', 'test');
    });
    expect(appendConsole).toHaveBeenCalledWith(expect.stringContaining('network failure'));
  });

  it('closePreview resets preview state to initial', async () => {
    setPywebview({
      read_html_content: vi.fn().mockResolvedValue({ ok: true, content: '<body><p>hi</p></body>' }),
      stream_media_file: vi.fn().mockResolvedValue({ ok: false }),
    });
    const { result } = renderHook(() => usePreview(makeOptions()));
    await act(async () => {
      await result.current.openPreview('/file.html', 'test', undefined, 'f1');
    });
    expect(result.current.preview.content).not.toBeNull();
    act(() => { result.current.closePreview(); });
    expect(result.current.preview.content).toBeNull();
    expect(result.current.preview.path).toBe('');
  });

  it('handleAudioStateChange updates editor session ref without re-rendering', () => {
    const { result } = renderHook(() => usePreview(makeOptions()));
    act(() => {
      result.current.handleAudioStateChange({ currentTime: 30, playbackRate: 1.5, volume: 0.8 });
    });
    expect(result.current.preview.content).toBeNull();
  });

  it('handleScrollTopChange updates scroll without re-rendering', () => {
    const { result } = renderHook(() => usePreview(makeOptions()));
    act(() => {
      result.current.handleScrollTopChange(200);
    });
    expect(result.current.preview.content).toBeNull();
  });

  it('relinkPreviewAudio does nothing when bridge unavailable', async () => {
    const { result } = renderHook(() => usePreview(makeOptions()));
    await act(async () => {
      await result.current.relinkPreviewAudio();
    });
    expect(result.current.preview.audioSrc).toBeNull();
  });

  it('relinkPreviewAudio links audio when bridge returns a file', async () => {
    const appendConsole = vi.fn();
    setPywebview({
      ask_media_file: vi.fn().mockResolvedValue({ path: '/audio.mp3', name: 'audio.mp3', size: 1024, duration: 60 }),
      stream_media_file: vi.fn().mockResolvedValue({ ok: true, url: 'blob:audio' }),
    });
    const { result } = renderHook(() => usePreview(makeOptions({ appendConsole })));
    await act(async () => {
      await result.current.relinkPreviewAudio();
    });
    expect(appendConsole).toHaveBeenCalledWith(expect.stringContaining('audio.mp3'));
  });

  it('openPreview loads audio when stream_media_file succeeds', async () => {
    setPywebview({
      read_html_content: vi.fn().mockResolvedValue({ ok: true, content: '<body>text</body>' }),
      stream_media_file: vi.fn().mockResolvedValue({ ok: true, url: 'blob:media' }),
    });
    const { result } = renderHook(() => usePreview(makeOptions()));
    await act(async () => {
      await result.current.openPreview('/file.html', 'test', '/audio.mp3', 'f1');
    });
    expect(result.current.preview.audioSrc).toBe('blob:media');
  });
});
