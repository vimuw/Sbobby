import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FileItem } from '../appState';
import { QueueSection } from './QueueSection';

function makeFile(overrides: Partial<FileItem> = {}): FileItem {
  return {
    id: 'f1',
    name: 'lezione.mp3',
    size: 1024,
    duration: 60,
    status: 'queued',
    progress: 0,
    phase: 0,
    ...overrides,
  };
}

const baseProps = {
  appState: 'idle' as const,
  autoContinue: false,
  setAutoContinue: vi.fn(),
  preferredModel: 'gemini-2.5-flash',
  queuedCount: 1,
  canStart: true,
  hasApiKey: true,
  isApiKeyValid: true,
  currentPhase: '',
  dndSensors: [],
  onDragEnd: vi.fn(),
  onRemove: vi.fn(),
  onRetry: vi.fn(),
  onPreview: vi.fn(),
  onOpenFile: vi.fn(),
  onStart: vi.fn(),
  onStop: vi.fn(),
};

describe('QueueSection', () => {
  it('renders nothing when no pending files and appState is idle', () => {
    render(<QueueSection {...baseProps} pendingFiles={[]} queuedCount={0} />);
    expect(screen.queryByText('Coda di elaborazione')).toBeNull();
  });

  it('shows queue heading when files are present', () => {
    render(<QueueSection {...baseProps} pendingFiles={[makeFile()]} />);
    expect(screen.getByText('Coda di elaborazione')).toBeTruthy();
  });

  it('shows file count pill', () => {
    render(<QueueSection {...baseProps} pendingFiles={[makeFile()]} />);
    expect(screen.getByText('1 elemento')).toBeTruthy();
  });

  it('shows plural "elementi" for multiple files', () => {
    const files = [makeFile({ id: 'f1' }), makeFile({ id: 'f2' })];
    render(<QueueSection {...baseProps} pendingFiles={files} queuedCount={2} />);
    expect(screen.getByText('2 elementi')).toBeTruthy();
  });

  it('shows model pill', () => {
    render(<QueueSection {...baseProps} pendingFiles={[makeFile()]} />);
    expect(screen.getByText(/Modello:/)).toBeTruthy();
  });

  it('shows start button when idle with canStart', () => {
    render(<QueueSection {...baseProps} pendingFiles={[makeFile()]} />);
    expect(screen.getByText(/Avvia sbobinatura/)).toBeTruthy();
  });

  it('calls onStart when start button is clicked', () => {
    const onStart = vi.fn();
    render(<QueueSection {...baseProps} pendingFiles={[makeFile()]} onStart={onStart} />);
    fireEvent.click(screen.getByText(/Avvia sbobinatura/));
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it('shows API key warning when hasApiKey is false', () => {
    render(<QueueSection {...baseProps} pendingFiles={[makeFile()]} hasApiKey={false} canStart={false} />);
    expect(screen.getByText(/Inserisci API Key/)).toBeTruthy();
  });

  it('shows invalid key warning when key is present but invalid', () => {
    render(
      <QueueSection
        {...baseProps}
        pendingFiles={[makeFile()]}
        hasApiKey isApiKeyValid={false} canStart={false}
      />,
    );
    expect(screen.getByText(/API Key non valida/)).toBeTruthy();
  });

  it('shows Stop button when processing', () => {
    render(
      <QueueSection
        {...baseProps}
        pendingFiles={[makeFile({ status: 'processing' })]}
        appState="processing"
      />,
    );
    expect(screen.getByText('Stop')).toBeTruthy();
  });

  it('calls onStop when Stop button is clicked', () => {
    const onStop = vi.fn();
    render(
      <QueueSection
        {...baseProps}
        pendingFiles={[makeFile({ status: 'processing' })]}
        appState="processing"
        onStop={onStop}
      />,
    );
    fireEvent.click(screen.getByText('Stop'));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it('shows "Annullamento in corso" when canceling', () => {
    render(
      <QueueSection
        {...baseProps}
        pendingFiles={[makeFile({ status: 'processing' })]}
        appState="canceling"
      />,
    );
    expect(screen.getAllByText('Annullamento in corso').length).toBeGreaterThan(0);
  });

  it('auto-continue toggle changes state', () => {
    const setAutoContinue = vi.fn();
    render(<QueueSection {...baseProps} pendingFiles={[makeFile()]} setAutoContinue={setAutoContinue} />);
    const toggle = screen.getByRole('switch');
    fireEvent.click(toggle);
    expect(setAutoContinue).toHaveBeenCalledTimes(1);
  });
});
