import { act, renderHook } from '@testing-library/react';
import { useRef } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useBridgeCallbacks } from './useBridgeCallbacks';
import type { AppStatus, FileItem, ProcessDonePayload, ProcessingAction } from '../appState';

function setPywebview(api: Record<string, unknown> | undefined) {
  Object.defineProperty(window, 'pywebview', {
    value: api === undefined ? undefined : { api },
    writable: true,
    configurable: true,
  });
}

describe('useBridgeCallbacks auto-continue', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setPywebview({});
    window.elSbobinatorBridge = null;
  });

  afterEach(() => {
    vi.useRealTimers();
    setPywebview(undefined);
    window.elSbobinatorBridge = null;
  });

  it('waits for the continuation start instead of forcing processing state early', async () => {
    const dispatch = vi.fn<(action: ProcessingAction) => void>();
    const startProcessing = vi.fn<(isContinuation?: boolean) => Promise<boolean>>().mockResolvedValue(true);
    const onFileContinued = vi.fn();
    const onBatchReset = vi.fn();
    const onBatchFullyDone = vi.fn<(data: ProcessDonePayload) => void>();
    const queuedFiles: FileItem[] = [{
      id: 'queued-1',
      name: 'lesson.mp3',
      size: 1,
      duration: 1,
      path: 'C:\\audio\\lesson.mp3',
      status: 'queued',
      progress: 0,
      phase: 0,
    }];

    renderHook(() => {
      const filesRef = useRef<FileItem[]>(queuedFiles);
      const appStateRef = useRef<AppStatus>('idle');
      const autoContinueRef = useRef(true);
      const startProcessingRef = useRef<(isContinuation?: boolean) => Promise<boolean>>(startProcessing);

      useBridgeCallbacks({
        dispatch,
        appendConsole: vi.fn(),
        filesRef,
        appStateRef,
        enqueueUniqueFiles: vi.fn(),
        setRegeneratePrompt: vi.fn(),
        setAskNewKeyPrompt: vi.fn(),
        autoContinueRef,
        startProcessingRef,
        onFileContinued,
        onBatchReset,
        onBatchFullyDone,
      });
    });

    const payload = { completed: 1, failed: 0, total: 2 };

    act(() => {
      window.elSbobinatorBridge?.processDone(payload);
    });

    expect(dispatch).toHaveBeenCalledWith({ type: 'bridge/process_done', data: payload });
    expect(dispatch).not.toHaveBeenCalledWith({ type: 'app/set_status', status: 'processing' });
    expect(onFileContinued).not.toHaveBeenCalled();
    expect(onBatchReset).not.toHaveBeenCalled();
    expect(onBatchFullyDone).not.toHaveBeenCalled();
    expect(startProcessing).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });

    expect(startProcessing).toHaveBeenCalledTimes(1);
    expect(startProcessing).toHaveBeenCalledWith(true);
    expect(onFileContinued).toHaveBeenCalledTimes(1);
    expect(onBatchReset).not.toHaveBeenCalled();
    expect(dispatch).not.toHaveBeenCalledWith({ type: 'app/set_status', status: 'processing' });
  });

  it('resets batch progress when the continuation never starts', async () => {
    const dispatch = vi.fn<(action: ProcessingAction) => void>();
    const startProcessing = vi.fn<(isContinuation?: boolean) => Promise<boolean>>().mockResolvedValue(false);
    const onFileContinued = vi.fn();
    const onBatchReset = vi.fn();
    const onBatchFullyDone = vi.fn<(data: ProcessDonePayload) => void>();
    const queuedFiles: FileItem[] = [{
      id: 'queued-1',
      name: 'lesson.mp3',
      size: 1,
      duration: 1,
      path: 'C:\\audio\\lesson.mp3',
      status: 'queued',
      progress: 0,
      phase: 0,
    }];

    renderHook(() => {
      const filesRef = useRef<FileItem[]>(queuedFiles);
      const appStateRef = useRef<AppStatus>('idle');
      const autoContinueRef = useRef(true);
      const startProcessingRef = useRef<(isContinuation?: boolean) => Promise<boolean>>(startProcessing);

      useBridgeCallbacks({
        dispatch,
        appendConsole: vi.fn(),
        filesRef,
        appStateRef,
        enqueueUniqueFiles: vi.fn(),
        setRegeneratePrompt: vi.fn(),
        setAskNewKeyPrompt: vi.fn(),
        autoContinueRef,
        startProcessingRef,
        onFileContinued,
        onBatchReset,
        onBatchFullyDone,
      });
    });

    act(() => {
      window.elSbobinatorBridge?.processDone({ completed: 1, failed: 0, total: 2 });
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });

    expect(startProcessing).toHaveBeenCalledWith(true);
    expect(onFileContinued).not.toHaveBeenCalled();
    expect(onBatchReset).toHaveBeenCalledTimes(1);
    expect(onBatchFullyDone).not.toHaveBeenCalled();
  });
});

function makeMinimalHook(overrides: Partial<Parameters<typeof useBridgeCallbacks>[0]> = {}) {
  const filesRef = { current: [] as FileItem[] };
  const appStateRef = { current: 'idle' as AppStatus };
  const autoContinueRef = { current: false };
  const startProcessingRef = { current: vi.fn<(isContinuation?: boolean) => Promise<boolean>>().mockResolvedValue(false) };
  const opts = {
    dispatch: vi.fn(),
    appendConsole: vi.fn(),
    filesRef: filesRef as unknown as ReturnType<typeof useRef<FileItem[]>>,
    appStateRef: appStateRef as unknown as ReturnType<typeof useRef<AppStatus>>,
    enqueueUniqueFiles: vi.fn(),
    setRegeneratePrompt: vi.fn(),
    setAskNewKeyPrompt: vi.fn(),
    autoContinueRef: autoContinueRef as unknown as ReturnType<typeof useRef<boolean>>,
    startProcessingRef: startProcessingRef as unknown as ReturnType<typeof useRef<(isContinuation?: boolean) => Promise<boolean>>>,
    onFileContinued: vi.fn(),
    onBatchReset: vi.fn(),
    onBatchFullyDone: vi.fn<(data: ProcessDonePayload) => void>(),
    ...overrides,
  };
  return opts;
}

describe('useBridgeCallbacks — direct bridge callbacks', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setPywebview({});
    window.elSbobinatorBridge = null;
  });
  afterEach(() => {
    vi.useRealTimers();
    setPywebview(undefined);
    window.elSbobinatorBridge = null;
  });

  it('appendConsole callback forwards message', () => {
    const appendConsole = vi.fn();
    const opts = makeMinimalHook({ appendConsole });
    renderHook(() => { useBridgeCallbacks(opts); });
    act(() => { window.elSbobinatorBridge?.appendConsole('hello'); });
    expect(appendConsole).toHaveBeenCalledWith('hello');
  });

  it('askRegenerate callback forwards data to setRegeneratePrompt', () => {
    const setRegeneratePrompt = vi.fn();
    const opts = makeMinimalHook({ setRegeneratePrompt });
    renderHook(() => { useBridgeCallbacks(opts); });
    act(() => { window.elSbobinatorBridge?.askRegenerate({ filename: 'test.mp3' }); });
    expect(setRegeneratePrompt).toHaveBeenCalledWith(expect.objectContaining({ filename: 'test.mp3' }));
  });

  it('askNewKey callback sets askNewKeyPrompt', () => {
    const setAskNewKeyPrompt = vi.fn();
    const opts = makeMinimalHook({ setAskNewKeyPrompt });
    renderHook(() => { useBridgeCallbacks(opts); });
    act(() => { window.elSbobinatorBridge?.askNewKey(); });
    expect(setAskNewKeyPrompt).toHaveBeenCalledWith(true);
  });

  it('filesDropped calls enqueueUniqueFiles when appState is idle', () => {
    const enqueueUniqueFiles = vi.fn();
    const opts = makeMinimalHook({ enqueueUniqueFiles });
    renderHook(() => { useBridgeCallbacks(opts); });
    act(() => {
      window.elSbobinatorBridge?.filesDropped([{ id: 'x', name: 'f.mp3', path: '/f.mp3', size: 100, duration: 30 }]);
    });
    expect(enqueueUniqueFiles).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ name: 'f.mp3' })]),
    );
  });

  it('fileDone callback: covers notification path for completed file', () => {
    const showNotification = vi.fn();
    setPywebview({ show_notification: showNotification });
    vi.spyOn(document, 'hasFocus').mockReturnValue(false);
    const doneFile: FileItem = {
      id: 'file-1', name: 'audio.mp3', size: 1, duration: 60, path: '/a.mp3', status: 'done', progress: 1, phase: 0,
    };
    const opts = makeMinimalHook();
    opts.filesRef = { current: [doneFile] } as unknown as ReturnType<typeof useRef<FileItem[]>>;
    renderHook(() => { useBridgeCallbacks(opts); });
    localStorage.removeItem('notifications_enabled');
    act(() => {
      window.elSbobinatorBridge?.fileDone({
        id: 'file-1', index: 0, output_html: '/out.html', output_dir: '/sessions/x', effective_model: 'gemini-2.5-flash',
      });
    });
    vi.restoreAllMocks();
  });

  it('processDone with no queued files and autoContinue=false calls onBatchFullyDone', async () => {
    const onBatchFullyDone = vi.fn<(data: ProcessDonePayload) => void>();
    const opts = makeMinimalHook({ onBatchFullyDone });
    renderHook(() => { useBridgeCallbacks(opts); });
    const payload = { completed: 1, failed: 0, total: 1 };
    act(() => { window.elSbobinatorBridge?.processDone(payload); });
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    expect(onBatchFullyDone).toHaveBeenCalledWith(payload);
  });
});
