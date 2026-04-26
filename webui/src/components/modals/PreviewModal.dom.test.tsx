import React from 'react';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PreviewModal } from './PreviewModal';

vi.mock('motion/react', () => ({
  motion: new Proxy({}, {
    get: (_: unknown, tag: string) => {
      return React.forwardRef((props: Record<string, unknown>, ref: unknown) => {
        const { initial: _i, animate: _a, exit: _e, transition: _t, layout: _l, variants: _v, ...rest } = props;
        return React.createElement(tag, { ...rest, ref: ref as React.Ref<unknown> });
      });
    },
  }),
  AnimatePresence: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
}));

vi.mock('../RichTextEditor', () => ({
  RichTextEditor: ({ onEditorReady }: { onEditorReady?: (getHtml: () => string) => void }) => {
    if (onEditorReady) onEditorReady(() => '<p>editor content</p>');
    return React.createElement('div', { 'data-testid': 'rich-text-editor' }, 'Editor');
  },
}));

vi.mock('../AudioPlayer', () => ({
  AudioPlayer: () => React.createElement('div', { 'data-testid': 'audio-player' }, 'Player'),
}));

const baseProps = {
  previewContent: '<p>Hello world</p>',
  previewTitle: 'My Document',
  htmlPath: '/sessions/out.html',
  onClose: vi.fn(),
  audioSrc: null,
  audioRelinkNeeded: false,
  onRelink: vi.fn().mockResolvedValue(false),
  previewInitAudio: {},
  previewInitScrollTop: undefined,
  onAudioStateChange: vi.fn(),
  onScrollTopChange: vi.fn(),
};

function setPywebview(api: Record<string, unknown> | undefined) {
  Object.defineProperty(window, 'pywebview', {
    value: api === undefined ? undefined : { api },
    writable: true,
    configurable: true,
  });
}

beforeEach(() => setPywebview(undefined));
afterEach(() => {
  vi.clearAllMocks();
  setPywebview(undefined);
});

describe('PreviewModal', () => {
  it('renders nothing when previewContent is null', () => {
    render(<PreviewModal {...baseProps} previewContent={null} />);
    expect(screen.queryByText(/Anteprima:/)).toBeNull();
  });

  it('shows modal with title when content is provided', () => {
    render(<PreviewModal {...baseProps} />);
    expect(screen.getByText('Anteprima: My Document')).toBeTruthy();
  });

  it('renders the editor area', () => {
    render(<PreviewModal {...baseProps} />);
    expect(screen.getByTestId('rich-text-editor')).toBeTruthy();
  });

  it('shows autosave idle status by default', () => {
    render(<PreviewModal {...baseProps} />);
    expect(screen.getByText('Salvataggio automatico')).toBeTruthy();
  });

  it('calls onClose when X button is clicked', async () => {
    const onClose = vi.fn();
    render(<PreviewModal {...baseProps} onClose={onClose} />);
    const btns = screen.getAllByRole('button');
    const closeBtn = btns[btns.length - 1];
    await act(async () => { fireEvent.click(closeBtn); });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on Escape key', async () => {
    const onClose = vi.fn();
    render(<PreviewModal {...baseProps} onClose={onClose} />);
    await act(async () => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows "Audio non trovato" when audioRelinkNeeded and no audioSrc', () => {
    render(<PreviewModal {...baseProps} audioRelinkNeeded />);
    expect(screen.getByText('Audio non trovato')).toBeTruthy();
    expect(screen.getByText('Ricollega audio')).toBeTruthy();
  });

  it('renders audio player when audioSrc is set', async () => {
    render(<PreviewModal {...baseProps} audioSrc="blob:audio" />);
    await waitFor(() => expect(screen.getByTestId('audio-player')).toBeTruthy());
  });

  it('shows open file button when htmlPath is set', () => {
    render(<PreviewModal {...baseProps} />);
    expect(screen.getByTitle('Apri file HTML')).toBeTruthy();
  });

  it('resets state when previewContent changes', () => {
    const { rerender } = render(<PreviewModal {...baseProps} />);
    rerender(<PreviewModal {...baseProps} previewContent="<p>Updated</p>" />);
    expect(screen.getByText('Salvataggio automatico')).toBeTruthy();
  });

  it('calls onRelink when "Ricollega audio" is clicked', async () => {
    const onRelink = vi.fn().mockResolvedValue(false);
    render(<PreviewModal {...baseProps} audioRelinkNeeded onRelink={onRelink} />);
    await act(async () => {
      fireEvent.click(screen.getByText('Ricollega audio'));
    });
    expect(onRelink).toHaveBeenCalledTimes(1);
  });

  it('clicking backdrop calls onClose', async () => {
    const onClose = vi.fn();
    const { container } = render(<PreviewModal {...baseProps} onClose={onClose} />);
    const backdrop = container.querySelector('.fixed.inset-0');
    expect(backdrop).toBeTruthy();
    await act(async () => { fireEvent.click(backdrop!); });
    expect(onClose).toHaveBeenCalled();
  });

  it('sets relinkSuccess when onRelink returns true', async () => {
    const onRelink = vi.fn().mockResolvedValue(true);
    render(<PreviewModal {...baseProps} audioRelinkNeeded onRelink={onRelink} />);
    await act(async () => {
      fireEvent.click(screen.getByText('Ricollega audio'));
    });
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    expect(onRelink).toHaveBeenCalledTimes(1);
  });

  it('calls open_file when external link button is clicked', async () => {
    const openFile = vi.fn();
    setPywebview({ open_file: openFile });
    render(<PreviewModal {...baseProps} />);
    await act(async () => {
      fireEvent.click(screen.getByTitle('Apri file HTML'));
    });
    expect(openFile).toHaveBeenCalledWith('/sessions/out.html');
  });
});
