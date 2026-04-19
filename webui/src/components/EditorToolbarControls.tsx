import React from 'react';
import { createPortal } from 'react-dom';
import { type Editor as TiptapEditor } from '@tiptap/core';
import { ChevronDown, Link2, Link2Off } from 'lucide-react';

export const COLOR_PALETTE: string[][] = [
  ['#000000', '#434343', '#666666', '#999999', '#b7b7b7', '#cccccc', '#d9d9d9', '#ffffff'],
  ['#ff0000', '#ff4500', '#ff9900', '#ffff00', '#00ff00', '#00ffff', '#4a86e8', '#9900ff'],
  ['#f4cccc', '#fce5cd', '#fff2cc', '#d9ead3', '#c9daf8', '#cfe2f3', '#d9d2e9', '#ead1dc'],
  ['#ea9999', '#f9cb9c', '#ffe599', '#b6d7a8', '#a4c2f4', '#9fc5e8', '#b4a7d6', '#d5a6bd'],
  ['#e06666', '#f6b26b', '#ffd966', '#93c47d', '#6d9eeb', '#6fa8dc', '#8e7cc3', '#c27ba0'],
  ['#cc0000', '#e69138', '#f1c232', '#6aa84f', '#3c78d8', '#3d85c8', '#674ea7', '#a64d79'],
  ['#990000', '#b45f06', '#bf9000', '#38761d', '#1155cc', '#0b5394', '#20124d', '#4c1130'],
];

export const HIGHLIGHT_COLORS = [
  { label: 'Giallo', color: '#fef08a' },
  { label: 'Verde', color: '#bbf7d0' },
  { label: 'Azzurro', color: '#bae6fd' },
  { label: 'Rosa', color: '#fecdd3' },
  { label: 'Arancione', color: '#fed7aa' },
  { label: 'Viola', color: '#e9d5ff' },
  { label: 'Nessuno', color: '#ffffff' },
];

const FONT_FAMILIES = [
  { label: 'Predefinito', value: '' },
  { label: 'Arial', value: 'Arial, sans-serif' },
  { label: 'Times New Roman', value: '"Times New Roman", serif' },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Courier New', value: '"Courier New", monospace' },
  { label: 'Verdana', value: 'Verdana, sans-serif' },
  { label: 'Trebuchet MS', value: '"Trebuchet MS", sans-serif' },
];

const FONT_SIZES = ['8', '9', '10', '11', '12', '14', '16', '18', '20', '24', '28', '32', '36', '48', '72'];

const HEADING_OPTIONS = [
  { label: 'Testo normale', value: 'paragraph' },
  { label: 'Titolo 1', value: 'h1' },
  { label: 'Titolo 2', value: 'h2' },
  { label: 'Titolo 3', value: 'h3' },
  { label: 'Titolo 4', value: 'h4' },
  { label: 'Titolo 5', value: 'h5' },
];

// Matches CSS: h1=1.5rem, h2=1.25rem, h3=1.1rem, h4=1rem, h5=0.9rem at 16px root
const HEADING_PX: Record<number, number> = { 1: 24, 2: 20, 3: 18, 4: 16, 5: 14 };

export const readFileAsDataUrl = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('Lettura immagine fallita.'));
    reader.readAsDataURL(file);
  });

export const ColorPickerButton = ({ editor }: { editor: TiptapEditor }) => {
  const [isOpen, setIsOpen] = React.useState(false);
  const [panelPos, setPanelPos] = React.useState({ top: 0, left: 0 });
  const buttonRef = React.useRef<HTMLButtonElement>(null);
  const panelRef = React.useRef<HTMLDivElement>(null);
  const currentColor: string | undefined = editor.getAttributes('textStyle').color;

  const toggleOpen = () => {
    if (!isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setPanelPos({ top: rect.bottom + 6, left: rect.left });
    }
    setIsOpen(prev => !prev);
  };

  React.useEffect(() => {
    if (!isOpen) return;
    const handler = (e: PointerEvent) => {
      const target = e.target as Node;
      if (buttonRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setIsOpen(false);
    };
    document.addEventListener('pointerdown', handler);
    return () => document.removeEventListener('pointerdown', handler);
  }, [isOpen]);

  const applyColor = (color: string, close = true) => {
    editor.chain().focus().setColor(color).run();
    if (close) setIsOpen(false);
  };

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={toggleOpen}
        className={`editor-button color-picker-btn${isOpen ? ' is-active' : ''}`}
        title="Colore testo"
      >
        <span className="color-picker-label">
          <span style={{ fontWeight: 700, fontSize: '0.8rem', lineHeight: 1, fontFamily: 'serif' }}>A</span>
          <span
            className="color-indicator"
            style={{ background: currentColor ?? 'var(--text-primary)', opacity: currentColor ? 1 : 0.55 }}
          />
        </span>
        <ChevronDown style={{ width: 9, height: 9, opacity: 0.55, flexShrink: 0 }} />
      </button>
      {isOpen && createPortal(
        <div
          ref={panelRef}
          className="color-picker-panel"
          style={{ position: 'fixed', top: panelPos.top, left: panelPos.left, zIndex: 9999 }}
        >
          {COLOR_PALETTE.map((row, ri) => (
            <div key={ri} className="color-row">
              {row.map(color => (
                <button
                  key={color}
                  type="button"
                  onPointerDown={e => { e.preventDefault(); applyColor(color); }}
                  className={`color-swatch${currentColor === color ? ' is-selected' : ''}`}
                  style={{ background: color }}
                  title={color}
                />
              ))}
            </div>
          ))}
          <div className="color-footer">
            <button
              type="button"
              onPointerDown={e => { e.preventDefault(); editor.chain().focus().unsetColor().run(); setIsOpen(false); }}
              className="color-reset"
            >
              ✕ Rimuovi colore
            </button>
            <label className="color-custom" title="Colore personalizzato">
              <span className="color-custom-preview" style={{ background: currentColor || '#888' }} />
              Personalizzato
              <input
                type="color"
                value={currentColor || '#888888'}
                onChange={e => applyColor(e.target.value, false)}
                style={{ position: 'absolute', opacity: 0, width: 0, height: 0, pointerEvents: 'none' }}
              />
            </label>
          </div>
        </div>,
        document.body
      )}
    </>
  );
};

export const HighlightPickerButton = ({ editor }: { editor: TiptapEditor }) => {
  const [isOpen, setIsOpen] = React.useState(false);
  const [panelPos, setPanelPos] = React.useState({ top: 0, left: 0 });
  const buttonRef = React.useRef<HTMLButtonElement>(null);
  const panelRef = React.useRef<HTMLDivElement>(null);
  const currentColor: string | undefined = editor.getAttributes('highlight').color;

  const toggleOpen = () => {
    if (!isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setPanelPos({ top: rect.bottom + 6, left: rect.left });
    }
    setIsOpen(prev => !prev);
  };

  React.useEffect(() => {
    if (!isOpen) return;
    const handler = (e: PointerEvent) => {
      const target = e.target as Node;
      if (buttonRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setIsOpen(false);
    };
    document.addEventListener('pointerdown', handler);
    return () => document.removeEventListener('pointerdown', handler);
  }, [isOpen]);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={toggleOpen}
        className={`editor-button color-picker-btn${isOpen || editor.isActive('highlight') ? ' is-active' : ''}`}
        title="Evidenziatore"
      >
        <span className="color-picker-label">
          <span style={{ fontWeight: 700, fontSize: '0.8rem', lineHeight: 1 }}>H</span>
          <span
            className="color-indicator"
            style={{ background: currentColor ?? '#fef08a', opacity: 0.9 }}
          />
        </span>
        <ChevronDown style={{ width: 9, height: 9, opacity: 0.55, flexShrink: 0 }} />
      </button>
      {isOpen && createPortal(
        <div
          ref={panelRef}
          className="color-picker-panel"
          style={{ position: 'fixed', top: panelPos.top, left: panelPos.left, zIndex: 9999 }}
        >
          <div className="color-row" style={{ flexWrap: 'wrap', gap: 5 }}>
            {HIGHLIGHT_COLORS.map(({ label, color }) => (
              <button
                key={color}
                type="button"
                onPointerDown={e => {
                  e.preventDefault();
                  if (color === '#ffffff') {
                    editor.chain().focus().unsetHighlight().run();
                  } else {
                    editor.chain().focus().toggleHighlight({ color }).run();
                  }
                  setIsOpen(false);
                }}
                className={`color-swatch${currentColor === color ? ' is-selected' : ''}`}
                style={{ background: color, border: color === '#ffffff' ? '1px solid #ccc' : undefined }}
                title={label}
              />
            ))}
          </div>
          <div className="color-footer" style={{ justifyContent: 'flex-start' }}>
            <button
              type="button"
              onPointerDown={e => { e.preventDefault(); editor.chain().focus().unsetHighlight().run(); setIsOpen(false); }}
              className="color-reset"
            >
              ✕ Rimuovi evidenziatore
            </button>
          </div>
        </div>,
        document.body
      )}
    </>
  );
};

export const FontFamilySelect = ({ editor }: { editor: TiptapEditor }) => {
  const currentFamily = editor.getAttributes('textStyle').fontFamily ?? '';
  return (
    <div className="editor-select-wrap">
      <select
        className="editor-select font-family-select"
        value={currentFamily}
        onChange={e => {
          if (e.target.value === '') {
            editor.chain().focus().unsetFontFamily().run();
          } else {
            editor.chain().focus().setFontFamily(e.target.value).run();
          }
        }}
        title="Carattere"
      >
        {FONT_FAMILIES.map(f => (
          <option key={f.label} value={f.value}>{f.label}</option>
        ))}
      </select>
      <ChevronDown className="editor-select-chevron" />
    </div>
  );
};

export const FontSizeSelect = ({ editor }: { editor: TiptapEditor }) => {
  const getCurrentSize = () => {
    if (!editor) return '';

    // 1. Explicit inline fontSize mark
    const fontSize = editor.getAttributes('textStyle').fontSize;
    if (fontSize) return fontSize.replace('px', '');

    // 2. Heading level — static lookup matching CSS rem values, no DOM read
    for (let i = 1; i <= 5; i++) {
      if (editor.isActive('heading', { level: i })) return String(HEADING_PX[i]);
    }

    // 3. Body text has no explicit size (11pt ≈ 14.67px, not in the dropdown)
    // Return '' so the select shows '—' rather than a wrong hardcoded value
    return '';
  };

  const currentSize = getCurrentSize();

  return (
    <div className="editor-select-wrap">
      <select
        className="editor-select font-size-select"
        value={currentSize}
        onChange={e => {
          if (e.target.value) {
            editor.chain().focus().setMark('textStyle', { fontSize: `${e.target.value}px` }).run();
          } else {
            editor.chain().focus().setMark('textStyle', { fontSize: null }).run();
          }
        }}
        title="Dimensione carattere"
      >
        <option value="">—</option>
        {FONT_SIZES.map(s => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <ChevronDown className="editor-select-chevron" />
    </div>
  );
};

export const HeadingSelect = ({ editor }: { editor: TiptapEditor }) => {
  let current = 'paragraph';
  for (let i = 1; i <= 5; i++) {
    if (editor.isActive('heading', { level: i })) { current = `h${i}`; break; }
  }
  return (
    <div className="editor-select-wrap">
      <select
        className="editor-select heading-select"
        value={current}
        onChange={e => {
          if (e.target.value === 'paragraph') {
            editor.chain().focus().setParagraph().run();
          } else {
            const level = parseInt(e.target.value.replace('h', '')) as 1 | 2 | 3 | 4 | 5;
            editor.chain().focus().setNode('heading', { level }).run();
          }
        }}
        title="Stile paragrafo"
      >
        {HEADING_OPTIONS.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <ChevronDown className="editor-select-chevron" />
    </div>
  );
};

export const LinkButton = ({ editor }: { editor: TiptapEditor }) => {
  const [isOpen, setIsOpen] = React.useState(false);
  const [url, setUrl] = React.useState('');
  const [panelPos, setPanelPos] = React.useState({ top: 0, left: 0 });
  const buttonRef = React.useRef<HTMLButtonElement>(null);
  const panelRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const isActive = editor.isActive('link');

  const openPanel = () => {
    if (isActive) {
      editor.chain().focus().unsetLink().run();
      return;
    }
    setUrl(editor.getAttributes('link').href ?? '');
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setPanelPos({ top: rect.bottom + 6, left: rect.left });
    }
    setIsOpen(true);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  React.useEffect(() => {
    if (!isOpen) return;
    const handler = (e: PointerEvent) => {
      const target = e.target as Node;
      if (buttonRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setIsOpen(false);
    };
    document.addEventListener('pointerdown', handler);
    return () => document.removeEventListener('pointerdown', handler);
  }, [isOpen]);

  const applyLink = () => {
    if (!url.trim()) return;
    const href = url.startsWith('http') ? url : `https://${url}`;
    editor.chain().focus().setLink({ href }).run();
    setIsOpen(false);
  };

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={openPanel}
        className={`editor-button${isActive ? ' is-active' : ''}`}
        title={isActive ? 'Rimuovi link' : 'Inserisci link'}
      >
        {isActive ? <Link2Off className="h-4 w-4" /> : <Link2 className="h-4 w-4" />}
      </button>
      {isOpen && createPortal(
        <div
          ref={panelRef}
          className="link-panel"
          style={{ position: 'fixed', top: panelPos.top, left: panelPos.left, zIndex: 9999 }}
        >
          <input
            ref={inputRef}
            type="url"
            placeholder="https://..."
            value={url}
            onChange={e => setUrl(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') applyLink();
              if (e.key === 'Escape') setIsOpen(false);
            }}
            className="link-input"
          />
          <button type="button" onClick={applyLink} className="link-apply-btn">Applica</button>
        </div>,
        document.body
      )}
    </>
  );
};
