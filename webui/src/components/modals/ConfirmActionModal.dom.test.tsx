import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConfirmActionModal } from './ConfirmActionModal';

const baseProps = {
  isOpen: true,
  title: 'Conferma azione',
  description: 'Sei sicuro di voler procedere?',
  confirmLabel: 'Elimina',
  onClose: vi.fn(),
  onConfirm: vi.fn(),
};

describe('ConfirmActionModal', () => {
  it('renders title and description when open', () => {
    render(<ConfirmActionModal {...baseProps} />);
    expect(screen.getByText('Conferma azione')).toBeTruthy();
    expect(screen.getByText('Sei sicuro di voler procedere?')).toBeTruthy();
  });

  it('renders confirm and cancel buttons', () => {
    render(<ConfirmActionModal {...baseProps} />);
    expect(screen.getByText('Elimina')).toBeTruthy();
    expect(screen.getByText('Annulla')).toBeTruthy();
  });

  it('uses custom cancelLabel when provided', () => {
    render(<ConfirmActionModal {...baseProps} cancelLabel="No grazie" />);
    expect(screen.getByText('No grazie')).toBeTruthy();
  });

  it('calls onConfirm when confirm button is clicked', () => {
    const onConfirm = vi.fn();
    render(<ConfirmActionModal {...baseProps} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByText('Elimina'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when cancel button is clicked', () => {
    const onClose = vi.fn();
    render(<ConfirmActionModal {...baseProps} onClose={onClose} />);
    fireEvent.click(screen.getByText('Annulla'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when X button is clicked', () => {
    const onClose = vi.fn();
    render(<ConfirmActionModal {...baseProps} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('Chiudi finestra'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders nothing when isOpen is false', () => {
    render(<ConfirmActionModal {...baseProps} isOpen={false} />);
    expect(screen.queryByText('Conferma azione')).toBeNull();
  });
});
