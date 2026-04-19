import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConsolePanel } from './ConsolePanel';

describe('ConsolePanel', () => {
  it('shows last console message when collapsed', () => {
    render(<ConsolePanel consoleLogs={[]} lastConsoleMessage="Ultimo messaggio" appState="idle" />);
    expect(screen.getByText('Ultimo messaggio')).toBeTruthy();
  });

  it('shows Console heading', () => {
    render(<ConsolePanel consoleLogs={[]} lastConsoleMessage="" appState="idle" />);
    expect(screen.getByText('Console')).toBeTruthy();
  });

  it('expands when expand button is clicked and shows log entries', () => {
    render(<ConsolePanel consoleLogs={['[12:00:00] log uno', 'log due']} lastConsoleMessage="" appState="idle" />);
    fireEvent.click(screen.getByTitle('Espandi'));
    expect(screen.getByText(/log uno/)).toBeTruthy();
    expect(screen.getByText(/log due/)).toBeTruthy();
  });

  it('shows copy button when expanded', () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
    render(<ConsolePanel consoleLogs={['a']} lastConsoleMessage="" appState="idle" />);
    fireEvent.click(screen.getByTitle('Espandi'));
    expect(screen.getByTitle('Copia tutto')).toBeTruthy();
  });

  it('collapses back when chevron is clicked again', () => {
    render(<ConsolePanel consoleLogs={[]} lastConsoleMessage="msg" appState="idle" />);
    fireEvent.click(screen.getByTitle('Espandi'));
    fireEvent.click(screen.getByTitle('Riduci'));
    expect(screen.getByText('msg')).toBeTruthy();
  });

  it('uses processing pulse when appState is processing', () => {
    const { container } = render(<ConsolePanel consoleLogs={[]} lastConsoleMessage="" appState="processing" />);
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
  });

  it('colors error log entries with error style', () => {
    render(<ConsolePanel consoleLogs={['Errore critico']} lastConsoleMessage="" appState="idle" />);
    fireEvent.click(screen.getByTitle('Espandi'));
    const entry = screen.getByText('Errore critico');
    expect(entry.style.color).toBeTruthy();
  });

  it('colors success log entries', () => {
    render(<ConsolePanel consoleLogs={['COMPLETATA operazione ✅']} lastConsoleMessage="" appState="idle" />);
    fireEvent.click(screen.getByTitle('Espandi'));
    expect(screen.getByText('COMPLETATA operazione ✅')).toBeTruthy();
  });

  it('clicking copy button writes to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });
    render(<ConsolePanel consoleLogs={['line1', 'line2']} lastConsoleMessage="" appState="idle" />);
    fireEvent.click(screen.getByTitle('Espandi'));
    fireEvent.click(screen.getByTitle('Copia tutto'));
    expect(writeText).toHaveBeenCalledWith('line1\nline2');
  });

  it('mouseEnter and mouseLeave on scroll area do not throw', () => {
    const { container } = render(<ConsolePanel consoleLogs={['msg']} lastConsoleMessage="" appState="idle" />);
    fireEvent.click(screen.getByTitle('Espandi'));
    const scrollArea = container.querySelector('.console-scroll') as HTMLElement;
    fireEvent.mouseEnter(scrollArea);
    fireEvent.mouseLeave(scrollArea);
  });
});
