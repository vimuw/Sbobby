import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ArchiveSession } from '../bridge';
import { ArchiveSection } from './ArchiveSection';

function makeSession(overrides: Partial<ArchiveSession> = {}): ArchiveSession {
  return {
    name: 'lezione-1',
    completed_at_iso: '2026-01-01T12:00:00Z',
    html_path: '/sessions/lezione-1/output.html',
    effective_model: 'gemini-flash',
    input_path: '/audio/lezione-1.mp3',
    session_dir: '/sessions/lezione-1',
    ...overrides,
  };
}

const baseProps = {
  onPreview: vi.fn(),
  onOpenFile: vi.fn(),
  onDeleteSession: vi.fn(),
};

describe('ArchiveSection', () => {
  it('renders nothing when sessions array is empty', () => {
    render(<ArchiveSection {...baseProps} sessions={[]} />);
    expect(screen.queryByText('Archivio Sbobine')).toBeNull();
  });

  it('shows archive header with session count', () => {
    render(<ArchiveSection {...baseProps} sessions={[makeSession()]} />);
    expect(screen.getByText('Archivio Sbobine')).toBeTruthy();
    expect(screen.getByText('1')).toBeTruthy();
  });

  it('expands list when header is clicked', () => {
    render(<ArchiveSection {...baseProps} sessions={[makeSession()]} />);
    fireEvent.click(screen.getByText('Archivio Sbobine'));
    expect(screen.getByPlaceholderText('Cerca per nome...')).toBeTruthy();
  });

  it('shows session name after expanding', () => {
    render(<ArchiveSection {...baseProps} sessions={[makeSession()]} />);
    fireEvent.click(screen.getByText('Archivio Sbobine'));
    expect(screen.getByText('lezione-1')).toBeTruthy();
  });

  it('calls onPreview when session row is clicked', () => {
    const onPreview = vi.fn();
    render(<ArchiveSection {...baseProps} sessions={[makeSession()]} onPreview={onPreview} />);
    fireEvent.click(screen.getByText('Archivio Sbobine'));
    fireEvent.click(screen.getByText('lezione-1'));
    expect(onPreview).toHaveBeenCalledWith(
      '/sessions/lezione-1/output.html',
      'lezione-1',
      '/audio/lezione-1.mp3',
      undefined,
      '/sessions/lezione-1',
    );
  });

  it('calls onDeleteSession when delete button is clicked', () => {
    const onDeleteSession = vi.fn();
    render(<ArchiveSection {...baseProps} sessions={[makeSession()]} onDeleteSession={onDeleteSession} />);
    fireEvent.click(screen.getByText('Archivio Sbobine'));
    fireEvent.click(screen.getByLabelText('Elimina sessione'));
    expect(onDeleteSession).toHaveBeenCalledWith('/sessions/lezione-1', 'lezione-1');
  });

  it('calls onOpenFile when external link button is clicked', () => {
    const onOpenFile = vi.fn();
    render(<ArchiveSection {...baseProps} sessions={[makeSession()]} onOpenFile={onOpenFile} />);
    fireEvent.click(screen.getByText('Archivio Sbobine'));
    fireEvent.click(screen.getByLabelText('Apri nel browser'));
    expect(onOpenFile).toHaveBeenCalledWith('/sessions/lezione-1/output.html');
  });

  it('filters sessions by search query', () => {
    const sessions = [
      makeSession({ name: 'fisica', session_dir: '/s/fisica' }),
      makeSession({ name: 'chimica', session_dir: '/s/chimica' }),
    ];
    render(<ArchiveSection {...baseProps} sessions={sessions} />);
    fireEvent.click(screen.getByText('Archivio Sbobine'));
    fireEvent.change(screen.getByPlaceholderText('Cerca per nome...'), { target: { value: 'fisica' } });
    expect(screen.getByText('fisica')).toBeTruthy();
  });

  it('shows "Nessun risultato" when search has no match', () => {
    render(<ArchiveSection {...baseProps} sessions={[makeSession()]} />);
    fireEvent.click(screen.getByText('Archivio Sbobine'));
    fireEvent.change(screen.getByPlaceholderText('Cerca per nome...'), { target: { value: 'zzz-nope' } });
    expect(screen.getByText(/Nessun risultato per/)).toBeTruthy();
  });

  it('shows pagination when sessions exceed 5', () => {
    const sessions = Array.from({ length: 7 }, (_, i) =>
      makeSession({ name: `lezione-${i}`, session_dir: `/s/${i}` }),
    );
    render(<ArchiveSection {...baseProps} sessions={sessions} />);
    fireEvent.click(screen.getByText('Archivio Sbobine'));
    expect(screen.getByLabelText('Pagina successiva')).toBeTruthy();
    expect(screen.getByText('1 / 2')).toBeTruthy();
  });

  it('navigates to next page when next button clicked', () => {
    const sessions = Array.from({ length: 7 }, (_, i) =>
      makeSession({ name: `lezione-${i}`, session_dir: `/s/${i}` }),
    );
    render(<ArchiveSection {...baseProps} sessions={sessions} />);
    fireEvent.click(screen.getByText('Archivio Sbobine'));
    fireEvent.click(screen.getByLabelText('Pagina successiva'));
    expect(screen.getByText('2 / 2')).toBeTruthy();
  });

  it('collapses when header is clicked again (isArchiveOpen toggles)', () => {
    render(<ArchiveSection {...baseProps} sessions={[makeSession()]} />);
    fireEvent.click(screen.getByText('Archivio Sbobine'));
    expect(screen.getByPlaceholderText('Cerca per nome...')).toBeTruthy();
    fireEvent.click(screen.getByText('Archivio Sbobine'));
  });

  it('toggles sort between Recente and Vecchia', () => {
    render(<ArchiveSection {...baseProps} sessions={[makeSession()]} />);
    fireEvent.click(screen.getByText('Archivio Sbobine'));
    expect(screen.getByText('Recente')).toBeTruthy();
    fireEvent.click(screen.getByTitle('Ordinate: più recenti prima'));
    expect(screen.getByText('Vecchia')).toBeTruthy();
  });
});
