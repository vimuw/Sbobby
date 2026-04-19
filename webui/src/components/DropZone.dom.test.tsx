import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DropZone } from './DropZone';

const baseProps = {
  isDragging: false,
  onDragOver: vi.fn(),
  onDragLeave: vi.fn(),
  onDrop: vi.fn(),
  onClick: vi.fn(),
};

describe('DropZone', () => {
  it('renders the browse text', () => {
    render(<DropZone {...baseProps} />);
    expect(screen.getByText('Clicca per sfogliare i file')).toBeTruthy();
  });

  it('mentions supported formats', () => {
    render(<DropZone {...baseProps} />);
    expect(screen.getByText(/\.mp3/)).toBeTruthy();
  });

  it('applies is-dragging class when isDragging is true', () => {
    const { container } = render(<DropZone {...baseProps} isDragging />);
    expect(container.querySelector('.is-dragging')).not.toBeNull();
  });

  it('does not apply is-dragging class when isDragging is false', () => {
    const { container } = render(<DropZone {...baseProps} />);
    expect(container.querySelector('.is-dragging')).toBeNull();
  });
});
