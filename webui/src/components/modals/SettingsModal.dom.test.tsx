import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SettingsModal } from './SettingsModal';

function setPywebview(api: Record<string, unknown> | undefined) {
  Object.defineProperty(window, 'pywebview', {
    value: api === undefined ? undefined : { api },
    writable: true,
    configurable: true,
  });
}

const makeProps = () => ({
  isOpen: true,
  onClose: vi.fn(),
  apiKey: 'AIzaSyTest123456',
  setApiKey: vi.fn(),
  fallbackKeys: [],
  setFallbackKeys: vi.fn(),
  preferredModel: 'gemini-3-flash-preview',
  setPreferredModel: vi.fn(),
  fallbackModels: [],
  setFallbackModels: vi.fn(),
  availableModels: [],
  appendConsole: vi.fn(),
});

beforeEach(() => {
  setPywebview(undefined);
});

afterEach(() => {
  setPywebview(undefined);
});

describe('SettingsModal — diagnostica chunk display', () => {
  it('shows default_chunk_minutes from availableModels registry for the primary model', async () => {
    const models = [
      { id: 'gemini-3-flash-preview', label: 'Gemini 3 Flash (Preview)', summary: '', default_chunk_minutes: 15 },
      { id: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash-Lite', summary: '', default_chunk_minutes: 10 },
    ];
    const { rerender } = render(
      <SettingsModal {...makeProps()} availableModels={models} preferredModel="gemini-3-flash-preview" />,
    );
    await act(async () => {
      fireEvent.click(screen.getByText('Avanzati').closest('button')!);
    });
    expect(screen.getByText('15 min')).toBeDefined();

    rerender(<SettingsModal {...makeProps()} availableModels={models} preferredModel="gemini-2.5-flash-lite" />);
    expect(screen.getByText('10 min')).toBeDefined();
  });
});

describe('SettingsModal — save behavior', () => {
  it('missing bridge: modal stays open, inline error displayed, console notified', async () => {
    const onClose = vi.fn();
    const appendConsole = vi.fn();

    render(<SettingsModal {...makeProps()} onClose={onClose} appendConsole={appendConsole} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Salva e Chiudi'));
    });

    expect(onClose).not.toHaveBeenCalled();
    expect(screen.queryByText(/non disponibile/i)).not.toBeNull();
    expect(appendConsole).toHaveBeenCalledTimes(1);
    expect(appendConsole).toHaveBeenCalledWith(
      expect.stringMatching(/❌.*non disponibile|non disponibile.*❌/s),
    );
  });

  it('save_settings returns {ok:false}: modal stays open and shows backend error', async () => {
    const mockSave = vi.fn().mockResolvedValue({ ok: false, error: 'quota esaurita' });
    setPywebview({ save_settings: mockSave });
    const onClose = vi.fn();

    render(<SettingsModal {...makeProps()} onClose={onClose} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Salva e Chiudi'));
    });

    expect(onClose).not.toHaveBeenCalled();
    expect(screen.queryByText(/quota esaurita/i)).not.toBeNull();
  });

  it('successful save: onClose called and no inline error shown', async () => {
    const mockSave = vi.fn().mockResolvedValue({ ok: true });
    setPywebview({ save_settings: mockSave });
    const onClose = vi.fn();

    render(<SettingsModal {...makeProps()} onClose={onClose} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Salva e Chiudi'));
    });

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/non disponibile/i)).toBeNull();
  });

  it('double-click: save_settings called only once, onClose called only once', async () => {
    let resolveFirst!: (val: { ok: boolean }) => void;
    const firstPromise = new Promise<{ ok: boolean }>(res => { resolveFirst = res; });
    const mockSave = vi.fn().mockReturnValueOnce(firstPromise);
    setPywebview({ save_settings: mockSave });
    const onClose = vi.fn();

    render(<SettingsModal {...makeProps()} onClose={onClose} />);

    const button = screen.getByText('Salva e Chiudi');
    fireEvent.click(button);
    fireEvent.click(button);

    await act(async () => { resolveFirst({ ok: true }); });

    expect(mockSave).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('backdrop click while saving: onClose NOT called', async () => {
    let resolveFirst!: (val: { ok: boolean }) => void;
    const firstPromise = new Promise<{ ok: boolean }>(res => { resolveFirst = res; });
    const mockSave = vi.fn().mockReturnValueOnce(firstPromise);
    setPywebview({ save_settings: mockSave });
    const onClose = vi.fn();

    const { container } = render(<SettingsModal {...makeProps()} onClose={onClose} />);

    fireEvent.click(screen.getByText('Salva e Chiudi'));

    const backdrop = container.querySelector('.absolute.inset-0') as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).not.toHaveBeenCalled();

    await act(async () => { resolveFirst({ ok: true }); });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('X button click while saving: onClose NOT called', async () => {
    let resolveFirst!: (val: { ok: boolean }) => void;
    const firstPromise = new Promise<{ ok: boolean }>(res => { resolveFirst = res; });
    const mockSave = vi.fn().mockReturnValueOnce(firstPromise);
    setPywebview({ save_settings: mockSave });
    const onClose = vi.fn();

    render(<SettingsModal {...makeProps()} onClose={onClose} />);

    fireEvent.click(screen.getByText('Salva e Chiudi'));

    const xButton = screen.getByLabelText('Chiudi impostazioni');
    fireEvent.click(xButton);
    expect(onClose).not.toHaveBeenCalled();

    await act(async () => { resolveFirst({ ok: true }); });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe('SettingsModal — session info race condition', () => {
  it('stale fetch discarded on open→close→reopen: loading not cleared prematurely', async () => {
    let resolveFirst!: (val: unknown) => void;
    let resolveSecond!: (val: unknown) => void;
    const firstPromise = new Promise(res => { resolveFirst = res; });
    const secondPromise = new Promise(res => { resolveSecond = res; });
    const mockGetInfo = vi.fn()
      .mockReturnValueOnce(firstPromise)
      .mockReturnValueOnce(secondPromise);
    setPywebview({ get_session_storage_info: mockGetInfo });

    const { rerender } = render(<SettingsModal {...makeProps()} isOpen={true} />);
    await act(async () => {
      fireEvent.click(screen.getByText('Avanzati').closest('button')!);
    });

    rerender(<SettingsModal {...makeProps()} isOpen={false} />);
    rerender(<SettingsModal {...makeProps()} isOpen={true} />);
    await act(async () => {
      fireEvent.click(screen.getByText('Avanzati').closest('button')!);
    });

    await act(async () => { resolveFirst({ ok: true, total_bytes: 999999, total_sessions: 7777 }); });

    expect(screen.queryByText('Calcolo…')).not.toBeNull();   // loading NOT prematurely cleared
    expect(screen.queryByText(/7777/)).toBeNull();            // stale data NOT applied

    await act(async () => { resolveSecond({ ok: true, total_bytes: 1024, total_sessions: 3 }); });

    expect(screen.queryByText('Calcolo…')).toBeNull();
    expect(screen.queryByText(/3 sessioni/)).not.toBeNull();
  });
});
