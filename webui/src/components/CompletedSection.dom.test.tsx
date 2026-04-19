import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FileItem } from '../appState';
import { CompletedSection } from './CompletedSection';

function makeFile(overrides: Partial<FileItem> = {}): FileItem {
  return {
    id: 'f1',
    name: 'lezione.mp3',
    size: 1024,
    duration: 60,
    status: 'done',
    progress: 100,
    phase: 3,
    ...overrides,
  };
}

const baseProps = {
  appState: 'idle' as const,
  onRemove: vi.fn(),
  onPreview: vi.fn(),
  onOpenFile: vi.fn(),
  onClearAll: vi.fn(),
};

describe('CompletedSection', () => {
  it('renders nothing when doneFiles is empty', () => {
    render(<CompletedSection {...baseProps} doneFiles={[]} />);
    expect(screen.queryByText('Sbobine completate')).toBeNull();
  });

  it('renders heading and file count when files are present', () => {
    render(<CompletedSection {...baseProps} doneFiles={[makeFile()]} />);
    expect(screen.getByText('Sbobine completate')).toBeTruthy();
    expect(screen.getByText('1 sbobina')).toBeTruthy();
  });

  it('uses plural "sbobine" for multiple files', () => {
    const files = [makeFile({ id: 'f1' }), makeFile({ id: 'f2' })];
    render(<CompletedSection {...baseProps} doneFiles={files} />);
    expect(screen.getByText('2 sbobine')).toBeTruthy();
  });

  it('renders "Pulisci tutto" button when appState is idle', () => {
    render(<CompletedSection {...baseProps} doneFiles={[makeFile()]} appState="idle" />);
    expect(screen.getByText('Pulisci tutto')).toBeTruthy();
  });

  it('renders "Pulisci tutto" during processing too', () => {
    render(<CompletedSection {...baseProps} doneFiles={[makeFile()]} appState="processing" />);
    expect(screen.getByText('Pulisci tutto')).toBeTruthy();
  });

  it('calls onClearAll when Pulisci tutto is clicked', () => {
    const onClearAll = vi.fn();
    render(<CompletedSection {...baseProps} doneFiles={[makeFile()]} onClearAll={onClearAll} />);
    fireEvent.click(screen.getByText('Pulisci tutto'));
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });

  it('shows search box when there are 5 or more files', () => {
    const files = Array.from({ length: 5 }, (_, i) => makeFile({ id: `f${i}`, name: `file-${i}.mp3` }));
    render(<CompletedSection {...baseProps} doneFiles={files} />);
    expect(screen.getByPlaceholderText('Cerca...')).toBeTruthy();
  });

  it('does not show search box for fewer than 5 files', () => {
    const files = [makeFile({ id: 'f1' }), makeFile({ id: 'f2' })];
    render(<CompletedSection {...baseProps} doneFiles={files} />);
    expect(screen.queryByPlaceholderText('Cerca...')).toBeNull();
  });

  it('filters files by search query — only matching file is active', () => {
    const files = [
      makeFile({ id: 'f1', name: 'fisica.mp3' }),
      makeFile({ id: 'f2', name: 'chimica.mp3' }),
      makeFile({ id: 'f3', name: 'biologia.mp3' }),
      makeFile({ id: 'f4', name: 'storia.mp3' }),
      makeFile({ id: 'f5', name: 'matematica.mp3' }),
    ];
    render(<CompletedSection {...baseProps} doneFiles={files} />);
    fireEvent.change(screen.getByPlaceholderText('Cerca...'), { target: { value: 'fisica' } });
    expect(screen.getByText('fisica.mp3')).toBeTruthy();
  });

  it('shows no-results message when search finds nothing', () => {
    const files = Array.from({ length: 5 }, (_, i) => makeFile({ id: `f${i}`, name: `file-${i}.mp3` }));
    render(<CompletedSection {...baseProps} doneFiles={files} />);
    fireEvent.change(screen.getByPlaceholderText('Cerca...'), { target: { value: 'xyz-nonexistent' } });
    expect(screen.getByText(/Nessun risultato per/)).toBeTruthy();
  });
});
