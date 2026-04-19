import { render, screen, fireEvent, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import App from './App';
import { useApiReady } from './hooks/useApiReady';

vi.mock('motion/react', () => ({
  motion: new Proxy({}, {
    get: (_: unknown, tag: string) => {
      return React.forwardRef((props: Record<string, unknown>, ref: unknown) => {
        const { initial: _i, animate: _a, exit: _e, transition: _t, layout: _l, variants: _v, layoutId: _li, whileTap: _wt, whileHover: _wh, ...rest } = props;
        return React.createElement(tag, { ...rest, ref: ref as React.Ref<unknown> });
      });
    },
  }),
  AnimatePresence: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
  useAnimation: () => ({ start: vi.fn(), stop: vi.fn() }),
  useMotionValue: (v: unknown) => ({ get: () => v, set: vi.fn() }),
}));

vi.mock('./hooks/useApiReady');

const mockApiReadyDefault = {
  apiReady: false,
  bridgeDelayed: false,
  apiKey: '',
  setApiKey: vi.fn(),
  hasProtectedKey: false,
  fallbackKeys: [],
  setFallbackKeys: vi.fn(),
  preferredModel: 'gemini-2.5-flash',
  setPreferredModel: vi.fn(),
  fallbackModels: [],
  setFallbackModels: vi.fn(),
  availableModels: [],
};

const mockApiReadyWithKey = {
  ...mockApiReadyDefault,
  apiReady: true,
  apiKey: 'AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345',
};

vi.mock('./hooks/useUpdateChecker', () => ({
  useUpdateChecker: () => ({ updateAvailable: null, latestVersion: null, isCheckingUpdate: false, checkForUpdates: vi.fn(), dismissUpdate: vi.fn() }),
}));

vi.mock('./hooks/useQueuePersistence', () => ({
  useQueuePersistence: vi.fn(),
}));

vi.mock('./hooks/useBridgeCallbacks', () => ({
  useBridgeCallbacks: vi.fn().mockReturnValue(undefined),
}));

vi.mock('./hooks/usePreview', () => ({
  usePreview: () => ({
    preview: { content: null, title: '', path: '', audioSrc: null, fileId: null, sourcePath: '', sessionDir: '', audioRelinkNeeded: false, initAudio: {} },
    openPreview: vi.fn(),
    closePreview: vi.fn(),
    relinkPreviewAudio: vi.fn(),
    handleAudioStateChange: vi.fn(),
    handleScrollTopChange: vi.fn(),
  }),
}));

vi.mock('./components/modals/PreviewModal', () => ({
  PreviewModal: () => null,
}));

function setPywebview(api: Record<string, unknown> | undefined) {
  Object.defineProperty(window, 'pywebview', {
    value: api === undefined ? undefined : { api },
    writable: true,
    configurable: true,
  });
}

function setElSbobinatorBridge() {
  const callbacks: Record<string, (...args: unknown[]) => void> = {};
  Object.defineProperty(window, 'elSbobinatorBridge', {
    value: {
      onSetCurrentFile: (cb: (...args: unknown[]) => void) => { callbacks['setCurrentFile'] = cb; },
      onFileDone: (cb: (...args: unknown[]) => void) => { callbacks['fileDone'] = cb; },
      onFileFailed: (cb: (...args: unknown[]) => void) => { callbacks['fileFailed'] = cb; },
      onProcessDone: (cb: (...args: unknown[]) => void) => { callbacks['processDone'] = cb; },
      onWorkTotals: (cb: (...args: unknown[]) => void) => { callbacks['workTotals'] = cb; },
      onWorkDone: (cb: (...args: unknown[]) => void) => { callbacks['workDone'] = cb; },
      onStepTime: (cb: (...args: unknown[]) => void) => { callbacks['stepTime'] = cb; },
      onAskNewKey: (cb: (...args: unknown[]) => void) => { callbacks['askNewKey'] = cb; },
    },
    writable: true,
    configurable: true,
  });
  return callbacks;
}

beforeEach(() => {
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
  localStorage.clear();
  setPywebview({ get_completed_sessions: vi.fn().mockResolvedValue({ ok: true, sessions: [] }) });
  setElSbobinatorBridge();
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('no network')));
  vi.mocked(useApiReady).mockReturnValue(mockApiReadyDefault);
});

afterEach(() => {
  localStorage.clear();
  setPywebview(undefined);
  vi.unstubAllGlobals();
});

describe('App', () => {
  it('renders the app header with logo', async () => {
    await act(async () => { render(<App />); });
    expect(screen.getByAltText('El Sbobinator')).toBeTruthy();
  });

  it('renders in setup mode when no API key is set', async () => {
    await act(async () => { render(<App />); });
    expect(screen.getByText('Configura la tua API Key')).toBeTruthy();
  });

  it('renders footer with GitHub link', async () => {
    await act(async () => { render(<App />); });
    expect(screen.getByText('GitHub')).toBeTruthy();
  });

  it('renders Ko-fi link in footer', async () => {
    await act(async () => { render(<App />); });
    expect(screen.getByText(/caffè/)).toBeTruthy();
  });

  it('shows API key input in setup mode', async () => {
    await act(async () => { render(<App />); });
    expect(screen.getByPlaceholderText(/Incolla qui la tua API Key/)).toBeTruthy();
  });

  it('shows advanced settings link in setup mode', async () => {
    await act(async () => { render(<App />); });
    expect(screen.getByText('Apri impostazioni avanzate')).toBeTruthy();
  });

  it('settings button opens settings modal', async () => {
    await act(async () => { render(<App />); });
    await act(async () => {
      fireEvent.click(screen.getByLabelText('Apri impostazioni'));
    });
    expect(screen.getByText(/Impostazioni/)).toBeTruthy();
  });

  it('console toggle button shows console panel', async () => {
    await act(async () => { render(<App />); });
    await act(async () => {
      fireEvent.click(screen.getByLabelText('Mostra console'));
    });
    expect(screen.getByText('Console')).toBeTruthy();
  });
});

describe('App — ready-empty mode (valid API key, no files)', () => {
  beforeEach(() => {
    vi.mocked(useApiReady).mockReturnValue(mockApiReadyWithKey);
  });

  it('shows DropZone when api key is valid and no files queued', async () => {
    await act(async () => { render(<App />); });
    expect(screen.getByText('Clicca per sfogliare i file')).toBeTruthy();
  });

  it('shows API ready status in header', async () => {
    await act(async () => { render(<App />); });
    expect(screen.getByText('API pronta')).toBeTruthy();
  });

  it('footer links are visible', async () => {
    await act(async () => { render(<App />); });
    expect(screen.getByText('GitHub')).toBeTruthy();
    expect(screen.getByText(/caffè/)).toBeTruthy();
  });

  it('console panel shows when console toggle is clicked', async () => {
    await act(async () => { render(<App />); });
    await act(async () => { fireEvent.click(screen.getByLabelText('Mostra console')); });
    expect(screen.getByText('Console')).toBeTruthy();
  });
});
