import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppHeader } from './AppHeader';

const baseProps = {
  apiReady: true,
  bridgeDelayed: false,
  hasApiKey: true,
  isApiKeyValid: true,
  appState: 'idle' as const,
  themeMode: 'dark' as const,
  setThemeMode: vi.fn(),
  showConsole: false,
  setShowConsole: vi.fn(),
  setIsSettingsOpen: vi.fn(),
  updateAvailable: null,
  dismissUpdate: vi.fn(),
};

function setPywebview(api: Record<string, unknown> | undefined) {
  Object.defineProperty(window, 'pywebview', {
    value: api === undefined ? undefined : { api },
    writable: true,
    configurable: true,
  });
}

beforeEach(() => {
  localStorage.clear();
  setPywebview(undefined);
});
afterEach(() => {
  localStorage.clear();
  setPywebview(undefined);
});

describe('AppHeader', () => {
  it('renders app logo', () => {
    render(<AppHeader {...baseProps} />);
    expect(screen.getByAltText('El Sbobinator')).toBeTruthy();
  });

  it('shows "API pronta" when api is ready with valid key', () => {
    render(<AppHeader {...baseProps} />);
    expect(screen.getByText('API pronta')).toBeTruthy();
  });

  it('shows "Bridge in avvio" when apiReady is false', () => {
    render(<AppHeader {...baseProps} apiReady={false} bridgeDelayed={false} />);
    expect(screen.getByText('Bridge in avvio')).toBeTruthy();
  });

  it('shows "Bridge in ritardo" when bridgeDelayed is true', () => {
    render(<AppHeader {...baseProps} apiReady={false} bridgeDelayed />);
    expect(screen.getByText('Bridge in ritardo')).toBeTruthy();
  });

  it('shows "Configura API" when no api key', () => {
    render(<AppHeader {...baseProps} hasApiKey={false} />);
    expect(screen.getByText('Configura API')).toBeTruthy();
  });

  it('shows "Chiave non valida" when key is invalid', () => {
    render(<AppHeader {...baseProps} isApiKeyValid={false} />);
    expect(screen.getByText('Chiave non valida')).toBeTruthy();
  });

  it('calls setThemeMode when theme toggle is clicked', () => {
    const setThemeMode = vi.fn();
    render(<AppHeader {...baseProps} setThemeMode={setThemeMode} />);
    fireEvent.click(screen.getByLabelText('Attiva tema chiaro'));
    expect(setThemeMode).toHaveBeenCalledTimes(1);
  });

  it('shows Sun icon in dark mode', () => {
    render(<AppHeader {...baseProps} themeMode="dark" />);
    expect(screen.getByTitle('Tema chiaro')).toBeTruthy();
  });

  it('shows Moon icon in light mode', () => {
    render(<AppHeader {...baseProps} themeMode="light" />);
    expect(screen.getByTitle('Tema scuro')).toBeTruthy();
  });

  it('calls setShowConsole when console button is clicked', () => {
    const setShowConsole = vi.fn();
    render(<AppHeader {...baseProps} setShowConsole={setShowConsole} />);
    fireEvent.click(screen.getByLabelText('Mostra console'));
    expect(setShowConsole).toHaveBeenCalledTimes(1);
  });

  it('calls setIsSettingsOpen when settings button is clicked', () => {
    const setIsSettingsOpen = vi.fn();
    render(<AppHeader {...baseProps} setIsSettingsOpen={setIsSettingsOpen} />);
    fireEvent.click(screen.getByLabelText('Apri impostazioni'));
    expect(setIsSettingsOpen).toHaveBeenCalledWith(true);
  });

  it('shows update banner when updateAvailable is set', () => {
    render(<AppHeader {...baseProps} updateAvailable="v2.0.0" />);
    expect(screen.getByText(/Nuova versione disponibile/)).toBeTruthy();
    expect(screen.getByText(/v2\.0\.0/)).toBeTruthy();
  });

  it('calls dismissUpdate when Ignora is clicked', () => {
    const dismissUpdate = vi.fn();
    render(<AppHeader {...baseProps} updateAvailable="v2.0.0" dismissUpdate={dismissUpdate} />);
    fireEvent.click(screen.getByLabelText('Chiudi avviso aggiornamento'));
    expect(dismissUpdate).toHaveBeenCalledWith('v2.0.0');
  });

  it('shows "Installa aggiornamento" button in update banner', () => {
    render(<AppHeader {...baseProps} updateAvailable="v2.0.0" />);
    expect(screen.getByText('Installa aggiornamento')).toBeTruthy();
  });

  it('shows console button as active when showConsole is true', () => {
    const { container } = render(<AppHeader {...baseProps} showConsole />);
    expect(container.querySelector('.icon-button--active')).not.toBeNull();
  });

  it('fires confetti on logo mouseEnter', async () => {
    const { container } = render(<AppHeader {...baseProps} />);
    const logoWrapper = container.querySelector('[alt="El Sbobinator"]')?.parentElement as HTMLElement;
    fireEvent.mouseEnter(logoWrapper);
    expect(logoWrapper).toBeTruthy();
  });

  it('calls download_and_install_update when install button is clicked', async () => {
    const downloadFn = vi.fn().mockResolvedValue({ ok: true });
    setPywebview({ download_and_install_update: downloadFn });
    render(<AppHeader {...baseProps} updateAvailable="v2.0.0" />);
    fireEvent.click(screen.getByText('Installa aggiornamento'));
    expect(downloadFn).toHaveBeenCalledWith('v2.0.0');
  });

  it('shows error state when download_and_install_update returns {ok:false}', async () => {
    const downloadFn = vi.fn().mockResolvedValue({ ok: false, error: 'disk full' });
    const openUrl = vi.fn();
    setPywebview({ download_and_install_update: downloadFn, open_url: openUrl });
    render(<AppHeader {...baseProps} updateAvailable="v2.0.0" />);
    fireEvent.click(screen.getByText('Installa aggiornamento'));
    await vi.waitFor(() => expect(openUrl).toHaveBeenCalled());
  });

  it('shows error state when download_and_install_update throws', async () => {
    const downloadFn = vi.fn().mockRejectedValue(new Error('network error'));
    const openUrl = vi.fn();
    setPywebview({ download_and_install_update: downloadFn, open_url: openUrl });
    render(<AppHeader {...baseProps} updateAvailable="v2.0.0" />);
    fireEvent.click(screen.getByText('Installa aggiornamento'));
    await vi.waitFor(() => expect(openUrl).toHaveBeenCalled());
  });

  it('shows peak-hour banner during peak hours', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T16:00:00'));
    localStorage.removeItem('peakBannerDismissedUntil');
    render(<AppHeader {...baseProps} />);
    expect(screen.getByText(/fascia oraria di punta/i)).toBeTruthy();
    vi.useRealTimers();
  });

  it('dismisses peak-hour banner on X click', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T16:00:00'));
    localStorage.removeItem('peakBannerDismissedUntil');
    render(<AppHeader {...baseProps} />);
    fireEvent.click(screen.getByLabelText('Chiudi avviso fascia oraria'));
    expect(localStorage.getItem('peakBannerDismissedUntil')).not.toBeNull();
    vi.useRealTimers();
  });
});
