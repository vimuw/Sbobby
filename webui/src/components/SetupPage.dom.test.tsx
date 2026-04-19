import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SetupPage } from './SetupPage';

const baseProps = {
  hasProtectedKey: false,
  setIsSettingsOpen: vi.fn(),
  onSaved: vi.fn(),
  preferredModel: 'gemini-2.5-flash',
  fallbackKeys: [],
  fallbackModels: [],
};

function setPywebview(api: Record<string, unknown> | undefined) {
  Object.defineProperty(window, 'pywebview', {
    value: api === undefined ? undefined : { api },
    writable: true,
    configurable: true,
  });
}

beforeEach(() => setPywebview(undefined));
afterEach(() => setPywebview(undefined));

describe('SetupPage', () => {
  it('shows "Configura la tua API Key" when no protected key', () => {
    render(<SetupPage {...baseProps} />);
    expect(screen.getByText('Configura la tua API Key')).toBeTruthy();
  });

  it('shows alternative text when hasProtectedKey is true', () => {
    render(<SetupPage {...baseProps} hasProtectedKey />);
    expect(screen.getByText('Chiave API non accessibile')).toBeTruthy();
  });

  it('shows password input by default', () => {
    render(<SetupPage {...baseProps} />);
    const input = screen.getByPlaceholderText(/Incolla qui la tua API Key/);
    expect((input as HTMLInputElement).type).toBe('password');
  });

  it('toggles input visibility on eye button click', () => {
    render(<SetupPage {...baseProps} />);
    const input = screen.getByPlaceholderText(/Incolla qui la tua API Key/) as HTMLInputElement;
    fireEvent.click(screen.getByLabelText('Mostra chiave'));
    expect(input.type).toBe('text');
    fireEvent.click(screen.getByLabelText('Nascondi chiave'));
    expect(input.type).toBe('password');
  });

  it('shows valid format hint for a valid AIzaSy key', () => {
    render(<SetupPage {...baseProps} />);
    fireEvent.change(screen.getByPlaceholderText(/Incolla qui la tua API Key/), {
      target: { value: 'AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345' },
    });
    expect(screen.getByText(/Formato valido/)).toBeTruthy();
  });

  it('shows invalid format warning for a bad key', () => {
    render(<SetupPage {...baseProps} />);
    fireEvent.change(screen.getByPlaceholderText(/Incolla qui la tua API Key/), {
      target: { value: 'bad-key' },
    });
    expect(screen.getByText(/Formato non valido/)).toBeTruthy();
  });

  it('Save button is disabled when key is empty', () => {
    render(<SetupPage {...baseProps} />);
    const btn = screen.getAllByText('Salva e inizia').find(
      el => el.closest('button') !== null,
    )?.closest('button') as HTMLButtonElement;
    expect(btn).toBeTruthy();
    expect(btn.disabled).toBe(true);
  });

  it('shows error when bridge is unavailable on save', async () => {
    render(<SetupPage {...baseProps} />);
    fireEvent.change(screen.getByPlaceholderText(/Incolla qui la tua API Key/), {
      target: { value: 'AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345' },
    });
    const saveBtn = screen.getAllByText('Salva e inizia').find(
      el => el.closest('button') !== null,
    )?.closest('button') as HTMLButtonElement;
    fireEvent.click(saveBtn);
    await vi.waitFor(() =>
      expect(screen.getByText(/Bridge Python non disponibile/)).toBeTruthy(),
    );
  });

  it('calls open_url when AI Studio link is clicked', () => {
    const openUrl = vi.fn();
    setPywebview({ open_url: openUrl });
    render(<SetupPage {...baseProps} />);
    fireEvent.click(screen.getByText('aistudio.google.com/apikey'));
    expect(openUrl).toHaveBeenCalledWith('https://aistudio.google.com/apikey');
  });

  it('calls setIsSettingsOpen when advanced settings link is clicked', () => {
    const setIsSettingsOpen = vi.fn();
    render(<SetupPage {...baseProps} setIsSettingsOpen={setIsSettingsOpen} />);
    fireEvent.click(screen.getByText('Apri impostazioni avanzate'));
    expect(setIsSettingsOpen).toHaveBeenCalledWith(true);
  });

  it('shows error when save_settings returns {ok:false}', async () => {
    const mockSave = vi.fn().mockResolvedValue({ ok: false, error: 'quota esaurita' });
    setPywebview({ save_settings: mockSave });
    render(<SetupPage {...baseProps} />);
    fireEvent.change(screen.getByPlaceholderText(/Incolla qui la tua API Key/), {
      target: { value: 'AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345' },
    });
    const saveBtn = screen.getAllByText('Salva e inizia').find(
      el => el.closest('button') !== null,
    )?.closest('button') as HTMLButtonElement;
    fireEvent.click(saveBtn);
    await vi.waitFor(() =>
      expect(screen.getByText(/quota esaurita/)).toBeTruthy(),
    );
  });

  it('calls onSaved when save_settings succeeds', async () => {
    const onSaved = vi.fn();
    const mockSave = vi.fn().mockResolvedValue({ ok: true });
    setPywebview({ save_settings: mockSave });
    render(<SetupPage {...baseProps} onSaved={onSaved} />);
    fireEvent.change(screen.getByPlaceholderText(/Incolla qui la tua API Key/), {
      target: { value: 'AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345' },
    });
    const saveBtn = screen.getAllByText('Salva e inizia').find(
      el => el.closest('button') !== null,
    )?.closest('button') as HTMLButtonElement;
    fireEvent.click(saveBtn);
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith('AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345'));
  });

  it('Enter key on valid input triggers save', async () => {
    const mockSave = vi.fn().mockResolvedValue({ ok: true });
    setPywebview({ save_settings: mockSave });
    render(<SetupPage {...baseProps} />);
    const input = screen.getByPlaceholderText(/Incolla qui la tua API Key/);
    fireEvent.change(input, { target: { value: 'AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await vi.waitFor(() => expect(mockSave).toHaveBeenCalledTimes(1));
  });

  it('Enter key on invalid input does NOT trigger save', async () => {
    const mockSave = vi.fn().mockResolvedValue({ ok: true });
    setPywebview({ save_settings: mockSave });
    render(<SetupPage {...baseProps} />);
    const input = screen.getByPlaceholderText(/Incolla qui la tua API Key/);
    fireEvent.change(input, { target: { value: 'bad-key' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await vi.waitFor(() => expect(mockSave).not.toHaveBeenCalled());
  });

  it('shows throw error when save_settings throws', async () => {
    const mockSave = vi.fn().mockRejectedValue(new Error('network error'));
    setPywebview({ save_settings: mockSave });
    render(<SetupPage {...baseProps} />);
    fireEvent.change(screen.getByPlaceholderText(/Incolla qui la tua API Key/), {
      target: { value: 'AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345' },
    });
    const saveBtn = screen.getAllByText('Salva e inizia').find(
      el => el.closest('button') !== null,
    )?.closest('button') as HTMLButtonElement;
    fireEvent.click(saveBtn);
    await vi.waitFor(() =>
      expect(screen.getByText(/network error/)).toBeTruthy(),
    );
  });
});
