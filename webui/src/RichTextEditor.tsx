import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Color } from '@tiptap/extension-color';
import { TextStyle } from '@tiptap/extension-text-style';
import Underline from '@tiptap/extension-underline';
import Highlight from '@tiptap/extension-highlight';
import TextAlign from '@tiptap/extension-text-align';
import FontFamily from '@tiptap/extension-font-family';
import Link from '@tiptap/extension-link';
import Subscript from '@tiptap/extension-subscript';
import Superscript from '@tiptap/extension-superscript';
import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import {
  AlignCenter, AlignJustify, AlignLeft, AlignRight,
  Bold, ChevronDown, Clipboard, Copy, ImagePlus, Italic,
  Link2, Link2Off, List, ListOrdered, Menu, MoreVertical, Quote, Redo,
  Scissors, Search, Strikethrough, Subscript as SubIcon,
  Superscript as SupIcon, Underline as UnderlineIcon, Undo, X,
} from 'lucide-react';
import { FloatingImage } from './FloatingImage';

export interface Heading {
  id: string;
  level: number;
  text: string;
}

interface RichTextEditorProps {
  initialContent: string;
  onChange?: (html: string) => void;
  onEditorReady?: (getHtml: () => string) => void;
  initialScrollTop?: number;
  onScrollTopChange?: (scrollTop: number) => void;
  onHeadingsChange?: (headings: Heading[]) => void;
  isTocOpen?: boolean;
  onTocToggle?: () => void;
  tocHeadings?: Heading[];
  onScrollToHeading?: (heading: Heading) => void;
}

const extractHeadings = (editor: any): Heading[] => {
  const json = editor.getJSON();
  const result: Heading[] = [];
  json.content?.forEach((node: any, idx: number) => {
    if (node.type === 'heading') {
      const text = node.content?.map((n: any) => n.text ?? '').join('') ?? '';
      if (text.trim()) result.push({ id: `h-${idx}`, level: node.attrs?.level ?? 2, text });
    }
  });
  return result;
};

const COLOR_PALETTE: string[][] = [
  ['#000000', '#434343', '#666666', '#999999', '#b7b7b7', '#cccccc', '#d9d9d9', '#ffffff'],
  ['#ff0000', '#ff4500', '#ff9900', '#ffff00', '#00ff00', '#00ffff', '#4a86e8', '#9900ff'],
  ['#f4cccc', '#fce5cd', '#fff2cc', '#d9ead3', '#c9daf8', '#cfe2f3', '#d9d2e9', '#ead1dc'],
  ['#ea9999', '#f9cb9c', '#ffe599', '#b6d7a8', '#a4c2f4', '#9fc5e8', '#b4a7d6', '#d5a6bd'],
  ['#e06666', '#f6b26b', '#ffd966', '#93c47d', '#6d9eeb', '#6fa8dc', '#8e7cc3', '#c27ba0'],
  ['#cc0000', '#e69138', '#f1c232', '#6aa84f', '#3c78d8', '#3d85c8', '#674ea7', '#a64d79'],
  ['#990000', '#b45f06', '#bf9000', '#38761d', '#1155cc', '#0b5394', '#20124d', '#4c1130'],
];

const HIGHLIGHT_COLORS = [
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

interface SearchHighlightPluginState {
  searchTerm: string;
  currentIndex: number;
  matchCase: boolean;
  decorations: DecorationSet;
}

const searchHighlightKey = new PluginKey<SearchHighlightPluginState>('searchHighlight');

const SearchHighlight = Extension.create({
  name: 'searchHighlight',

  addCommands() {
    return {
      setSearchTerm:
        (term: string, currentIndex = -1, matchCase = false) =>
        ({ view }: { view: any }) => {
          view.dispatch(
            view.state.tr.setMeta(searchHighlightKey, { term, currentIndex, matchCase }),
          );
          return true;
        },
    } as any;
  },

  addProseMirrorPlugins() {
    return [
      new Plugin<SearchHighlightPluginState>({
        key: searchHighlightKey,
        state: {
          init(): SearchHighlightPluginState {
            return { searchTerm: '', currentIndex: -1, matchCase: false, decorations: DecorationSet.empty };
          },
          apply(tr, value, _old, newState): SearchHighlightPluginState {
            const meta = tr.getMeta(searchHighlightKey) as
              | { term: string; currentIndex: number; matchCase?: boolean }
              | undefined;
            const searchTerm = meta !== undefined ? meta.term : value.searchTerm;
            const currentIndex = meta !== undefined ? meta.currentIndex : value.currentIndex;
            const matchCase = meta !== undefined ? (meta.matchCase ?? false) : value.matchCase;

            if (!searchTerm) {
              return { searchTerm: '', currentIndex: -1, matchCase: false, decorations: DecorationSet.empty };
            }

            if (meta === undefined && !tr.docChanged) {
              return { searchTerm, currentIndex, matchCase, decorations: value.decorations.map(tr.mapping, tr.doc) };
            }

            const decorations: Decoration[] = [];
            const searchStr = matchCase ? searchTerm : searchTerm.toLowerCase();
            let matchIdx = 0;

            newState.doc.descendants((node: any, pos: number) => {
              if (!node.isText || !node.text) return;
              const nodeText = matchCase ? node.text : node.text.toLowerCase();
              let idx = 0;
              while ((idx = nodeText.indexOf(searchStr, idx)) !== -1) {
                decorations.push(
                  Decoration.inline(pos + idx, pos + idx + searchTerm.length, {
                    class:
                      matchIdx === currentIndex
                        ? 'search-highlight-active'
                        : 'search-highlight',
                  }),
                );
                idx += searchStr.length;
                matchIdx++;
              }
            });

            return {
              searchTerm,
              currentIndex,
              matchCase,
              decorations: DecorationSet.create(newState.doc, decorations),
            };
          },
        },
        props: {
          decorations(state) {
            return searchHighlightKey.getState(state)?.decorations ?? DecorationSet.empty;
          },
        },
      }),
    ];
  },
});

const FontSize = Extension.create({
  name: 'fontSize',
  addGlobalAttributes() {
    return [{
      types: ['textStyle'],
      attributes: {
        fontSize: {
          default: null,
          parseHTML: el => (el as HTMLElement).style.fontSize || null,
          renderHTML: attrs => attrs.fontSize ? { style: `font-size: ${attrs.fontSize}` } : {},
        },
      },
    }];
  },
});

const ColorPickerButton = ({ editor }: { editor: any }) => {
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

const readFileAsDataUrl = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('Lettura immagine fallita.'));
    reader.readAsDataURL(file);
  });

const HighlightPickerButton = ({ editor }: { editor: any }) => {
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

const FontFamilySelect = ({ editor }: { editor: any }) => {
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

// Matches CSS: h1=1.5rem, h2=1.25rem, h3=1.1rem, h4=1rem, h5=0.9rem at 16px root
const HEADING_PX: Record<number, number> = { 1: 24, 2: 20, 3: 18, 4: 16, 5: 14 };

const FontSizeSelect = ({ editor }: { editor: any }) => {
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

const HeadingSelect = ({ editor }: { editor: any }) => {
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

const LinkButton = ({ editor }: { editor: any }) => {
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

const menuBarStateKey = (editor: any): string => [
  editor.isActive('bold'),
  editor.isActive('italic'),
  editor.isActive('underline'),
  editor.isActive('strike'),
  editor.isActive('highlight'),
  editor.isActive('subscript'),
  editor.isActive('superscript'),
  editor.isActive('link'),
  editor.isActive('heading', { level: 1 }),
  editor.isActive('heading', { level: 2 }),
  editor.isActive('heading', { level: 3 }),
  editor.isActive('heading', { level: 4 }),
  editor.isActive('heading', { level: 5 }),
  editor.isActive('bulletList'),
  editor.isActive('orderedList'),
  editor.isActive('blockquote'),
  editor.isActive({ textAlign: 'center' }),
  editor.isActive({ textAlign: 'right' }),
  editor.isActive({ textAlign: 'justify' }),
  editor.can().undo(),
  editor.can().redo(),
  editor.getAttributes('highlight').color ?? '',
  editor.getAttributes('textStyle').color ?? '',
  editor.getAttributes('textStyle').fontFamily ?? '',
  editor.getAttributes('textStyle').fontSize ?? '',
].join('|');

const MenuBar = ({
  editor,
  onInsertImages,
  showFindReplace,
  onToggleFindReplace,
}: {
  editor: any;
  onInsertImages: (files: FileList | File[]) => void;
  showFindReplace: boolean;
  onToggleFindReplace: () => void;
}) => {
  const [, forceUpdate] = React.useState({});
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const prevMenuKeyRef = useRef('');

  React.useEffect(() => {
    if (!editor) return;
    const handleTransaction = () => {
      const key = menuBarStateKey(editor);
      if (key !== prevMenuKeyRef.current) {
        prevMenuKeyRef.current = key;
        forceUpdate({});
      }
    };
    editor.on('transaction', handleTransaction);
    return () => { editor.off('transaction', handleTransaction); };
  }, [editor]);

  if (!editor) return null;
  const btn = (active: boolean) => `editor-button${active ? ' is-active' : ''}`;

  return (
    <div className="editor-toolbar">
      <button type="button" onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()} className="editor-button" title="Annulla (Ctrl+Z)">
        <Undo className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()} className="editor-button" title="Ripeti (Ctrl+Y)">
        <Redo className="h-4 w-4" />
      </button>
      <div className="editor-separator" />
      <HeadingSelect editor={editor} />
      <div className="editor-separator" />
      <FontFamilySelect editor={editor} />
      <FontSizeSelect editor={editor} />
      <div className="editor-separator" />
      <button type="button" onClick={() => editor.chain().focus().toggleBold().run()} className={btn(editor.isActive('bold'))} title="Grassetto (Ctrl+B)">
        <Bold className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().toggleItalic().run()} className={btn(editor.isActive('italic'))} title="Corsivo (Ctrl+I)">
        <Italic className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().toggleUnderline().run()} className={btn(editor.isActive('underline'))} title="Sottolineato (Ctrl+U)">
        <UnderlineIcon className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().toggleStrike().run()} className={btn(editor.isActive('strike'))} title="Barrato">
        <Strikethrough className="h-4 w-4" />
      </button>
      <ColorPickerButton editor={editor} />
      <HighlightPickerButton editor={editor} />
      <div className="editor-separator" />
      <LinkButton editor={editor} />
      <button type="button" onClick={() => imageInputRef.current?.click()} className="editor-button" title="Inserisci immagine">
        <ImagePlus className="h-4 w-4" />
      </button>
      <div className="editor-separator" />
      <button type="button" onClick={() => editor.chain().focus().setTextAlign('left').run()} className={btn(editor.isActive({ textAlign: 'left' }))} title="Allinea sinistra">
        <AlignLeft className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().setTextAlign('center').run()} className={btn(editor.isActive({ textAlign: 'center' }))} title="Centra">
        <AlignCenter className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().setTextAlign('right').run()} className={btn(editor.isActive({ textAlign: 'right' }))} title="Allinea destra">
        <AlignRight className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().setTextAlign('justify').run()} className={btn(editor.isActive({ textAlign: 'justify' }))} title="Giustifica">
        <AlignJustify className="h-4 w-4" />
      </button>
      <div className="editor-separator" />
      <button type="button" onClick={() => editor.chain().focus().toggleBulletList().run()} className={btn(editor.isActive('bulletList'))} title="Elenco puntato">
        <List className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().toggleOrderedList().run()} className={btn(editor.isActive('orderedList'))} title="Elenco numerato">
        <ListOrdered className="h-4 w-4" />
      </button>
      <div className="editor-separator" />
      <button type="button" onClick={() => editor.chain().focus().toggleBlockquote().run()} className={btn(editor.isActive('blockquote'))} title="Citazione">
        <Quote className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().toggleSubscript().run()} className={btn(editor.isActive('subscript'))} title="Pedice">
        <SubIcon className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().toggleSuperscript().run()} className={btn(editor.isActive('superscript'))} title="Apice">
        <SupIcon className="h-4 w-4" />
      </button>
      <div className="editor-separator" />
      <button
        type="button"
        onClick={onToggleFindReplace}
        className={btn(showFindReplace)}
        title="Trova e sostituisci (Ctrl+H)"
      >
        <Search className="h-4 w-4" />
      </button>

      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={event => {
          if (event.target.files?.length) {
            onInsertImages(event.target.files);
          }
          event.currentTarget.value = '';
        }}
      />
    </div>
  );
};

const FindReplacePanel = ({
  editor,
  onClose,
  initialMode,
  focusTrigger,
}: {
  editor: any;
  onClose: () => void;
  initialMode: 'find' | 'replace';
  focusTrigger?: number;
}) => {
  const [expanded, setExpanded] = useState(initialMode === 'replace');
  const [findText, setFindText] = useState('');
  const [replaceText, setReplaceText] = useState('');
  const [matchCount, setMatchCount] = useState(0);
  const [currentMatch, setCurrentMatch] = useState(0);
  const [matchCase, setMatchCase] = useState(false);
  const matchesRef = useRef<{ from: number; to: number }[]>([]);
  const currentMatchRef = useRef(0);
  const findInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    findInputRef.current?.focus({ preventScroll: true });
    return () => { editor.commands.setSearchTerm('', -1, false); };
  }, [editor]);

  useEffect(() => {
    if (focusTrigger !== undefined && focusTrigger > 0) {
      findInputRef.current?.focus({ preventScroll: true });
    }
  }, [focusTrigger]);

  useEffect(() => {
    if (initialMode === 'replace') setExpanded(true);
  }, [initialMode]);

  const buildMatches = useCallback((text: string, caseFlag: boolean) => {
    if (!editor || !text) return [];
    const results: { from: number; to: number }[] = [];
    const searchStr = caseFlag ? text : text.toLowerCase();
    editor.state.doc.descendants((node: any, pos: number) => {
      if (!node.isText || !node.text) return;
      const nodeText = caseFlag ? node.text : node.text.toLowerCase();
      let idx = 0;
      while ((idx = nodeText.indexOf(searchStr, idx)) !== -1) {
        results.push({ from: pos + idx, to: pos + idx + text.length });
        idx += searchStr.length;
      }
    });
    return results;
  }, [editor]);

  const updateSearch = useCallback((text: string, curIdx = -1, caseFlag = matchCase) => {
    const matches = buildMatches(text, caseFlag);
    matchesRef.current = matches;
    setMatchCount(matches.length);
    editor.commands.setSearchTerm(text, curIdx, caseFlag);
    return matches;
  }, [editor, buildMatches, matchCase]);

  const scrollToMatch = useCallback((matches: { from: number; to: number }[], idx: number, text = findText, caseFlag = matchCase) => {
    if (!matches.length || !editor) return;
    currentMatchRef.current = idx + 1;
    setCurrentMatch(idx + 1);
    editor.commands.setSearchTerm(text, idx, caseFlag);
    requestAnimationFrame(() => {
      const activeEl = editor.view.dom.querySelector('.search-highlight-active');
      if (activeEl) activeEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      findInputRef.current?.focus({ preventScroll: true });
    });
  }, [editor, findText, matchCase]);

  const handleNext = useCallback(() => {
    const matches = matchesRef.current.length ? matchesRef.current : buildMatches(findText, matchCase);
    if (!matches.length) return;
    const next = currentMatchRef.current >= matches.length ? 0 : currentMatchRef.current;
    scrollToMatch(matches, next);
  }, [findText, matchCase, buildMatches, scrollToMatch]);

  const handlePrev = useCallback(() => {
    const matches = matchesRef.current.length ? matchesRef.current : buildMatches(findText, matchCase);
    if (!matches.length) return;
    const prev = currentMatchRef.current <= 1 ? matches.length - 1 : currentMatchRef.current - 2;
    scrollToMatch(matches, prev);
  }, [findText, matchCase, buildMatches, scrollToMatch]);

  const handleReplace = () => {
    if (!editor || !findText || !matchesRef.current.length) return;
    const { from, to } = editor.state.selection;
    const selectedText = editor.state.doc.textBetween(from, to);
    const isMatch = matchCase
      ? selectedText === findText
      : selectedText.toLowerCase() === findText.toLowerCase();
    if (isMatch) {
      const tr = editor.state.tr;
      if (replaceText) {
        editor.view.dispatch(tr.replaceWith(from, to, editor.schema.text(replaceText)));
      } else {
        editor.view.dispatch(tr.delete(from, to));
      }
      const newMatches = updateSearch(findText, -1);
      if (newMatches.length) scrollToMatch(newMatches, Math.min(currentMatchRef.current - 1, newMatches.length - 1));
    } else {
      handleNext();
    }
  };

  const handleReplaceAll = () => {
    if (!editor || !findText) return;
    const matches = buildMatches(findText, matchCase);
    if (!matches.length) return;
    const sortedMatches = [...matches].sort((a, b) => b.from - a.from);
    const tr = editor.state.tr;
    for (const m of sortedMatches) {
      if (replaceText) {
        tr.replaceWith(m.from, m.to, editor.schema.text(replaceText));
      } else {
        tr.delete(m.from, m.to);
      }
    }
    editor.view.dispatch(tr);
    matchesRef.current = [];
    currentMatchRef.current = 0;
    setMatchCount(0);
    setCurrentMatch(0);
    editor.commands.setSearchTerm('', -1, false);
    requestAnimationFrame(() => findInputRef.current?.focus({ preventScroll: true }));
  };

  const handleMatchCaseChange = (checked: boolean) => {
    setMatchCase(checked);
    currentMatchRef.current = 0;
    setCurrentMatch(0);
    updateSearch(findText, -1, checked);
  };

  const findInputChange = (val: string) => {
    setFindText(val);
    currentMatchRef.current = 0;
    setCurrentMatch(0);
    updateSearch(val, -1);
  };

  if (!expanded) {
    return (
      <div className="find-bar-float">
        <input
          ref={findInputRef}
          type="text"
          placeholder="Trova nel documento..."
          value={findText}
          onChange={e => findInputChange(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') { e.preventDefault(); e.shiftKey ? handlePrev() : handleNext(); }
            if (e.key === 'Escape') onClose();
          }}
          className="find-bar-input"
        />
        <span className="find-bar-count">
          {findText ? (matchCount > 0 ? `${currentMatch} di ${matchCount}` : 'Nessun risultato') : ''}
        </span>
        <button type="button" onClick={handlePrev} className="find-bar-btn" title="Precedente (Shift+Invio)" disabled={matchCount === 0}>
          <ChevronDown style={{ transform: 'rotate(180deg)', width: 15, height: 15 }} />
        </button>
        <button type="button" onClick={handleNext} className="find-bar-btn" title="Successivo (Invio)" disabled={matchCount === 0}>
          <ChevronDown style={{ width: 15, height: 15 }} />
        </button>
        <button type="button" onClick={() => setExpanded(true)} className="find-bar-btn" title="Trova e sostituisci">
          <MoreVertical style={{ width: 15, height: 15 }} />
        </button>
        <button type="button" onClick={onClose} className="find-bar-btn" title="Chiudi (Esc)">
          <X style={{ width: 15, height: 15 }} />
        </button>
      </div>
    );
  }

  return (
    <div className="find-replace-dialog">
      <div className="find-replace-dialog-header">
        <span className="find-replace-dialog-title">Trova e sostituisci</span>
        <button type="button" onClick={onClose} className="find-bar-btn" title="Chiudi (Esc)">
          <X style={{ width: 16, height: 16 }} />
        </button>
      </div>
      <div className="find-replace-dialog-body">
        <div className="find-replace-dialog-field">
          <label className="find-replace-dialog-label">Trova</label>
          <input
            ref={findInputRef}
            type="text"
            value={findText}
            onChange={e => findInputChange(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') { e.preventDefault(); handleNext(); }
              if (e.key === 'Escape') onClose();
            }}
            className="find-replace-dialog-input"
          />
          {findText && (
            <span className="find-replace-dialog-count">
              {matchCount > 0 ? `${currentMatch} di ${matchCount}` : 'Nessun risultato'}
            </span>
          )}
        </div>
        <div className="find-replace-dialog-field">
          <input
            type="text"
            placeholder="Sostituisci con..."
            value={replaceText}
            onChange={e => setReplaceText(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') { e.preventDefault(); handleReplace(); }
              if (e.key === 'Escape') onClose();
            }}
            className="find-replace-dialog-input"
          />
        </div>
        <label className="find-replace-dialog-check">
          <input type="checkbox" checked={matchCase} onChange={e => handleMatchCaseChange(e.target.checked)} />
          <span>Maiuscole/minuscole</span>
        </label>
        <div className="find-replace-dialog-actions">
          <button type="button" onClick={handleReplace} disabled={matchCount === 0} className="find-replace-dialog-btn">
            Sostituisci
          </button>
          <button type="button" onClick={handleReplaceAll} disabled={matchCount === 0} className="find-replace-dialog-btn">
            Sostituisci tutto
          </button>
          <button type="button" onClick={handlePrev} disabled={matchCount === 0} className="find-replace-dialog-btn">
            Precedente
          </button>
          <button type="button" onClick={handleNext} disabled={matchCount === 0} className="find-replace-dialog-btn find-replace-dialog-btn-primary">
            Successivo
          </button>
        </div>
      </div>
    </div>
  );
};

const WordCount = ({ editor }: { editor: any }) => {
  const [counts, setCounts] = React.useState({ words: 0, chars: 0 });
  React.useEffect(() => {
    if (!editor) return;
    let timer: number | null = null;
    const update = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const text = editor.state.doc.textContent;
        const words = text.trim() ? text.trim().split(/\s+/).length : 0;
        setCounts({ words, chars: text.length });
      }, 500);
    };
    editor.on('update', update);
    update();
    return () => { editor.off('update', update); if (timer !== null) window.clearTimeout(timer); };
  }, [editor]);

  return (
    <div className="editor-wordcount">
      <span>{counts.words} {counts.words === 1 ? 'parola' : 'parole'}</span>
      <span className="editor-wordcount-sep">·</span>
      <span>{counts.chars} caratteri</span>
    </div>
  );
};

export function RichTextEditor({ initialContent, onChange, onEditorReady, initialScrollTop, onScrollTopChange, onHeadingsChange, isTocOpen = false, onTocToggle, tocHeadings = [], onScrollToHeading }: RichTextEditorProps) {
  const [contextMenu, setContextMenu] = React.useState<{ x: number; y: number } | null>(null);
  const [findMode, setFindMode] = useState<null | 'find' | 'replace'>(null);
  const [findFocusTrigger, setFindFocusTrigger] = useState(0);
  const findModeRef = useRef<null | 'find' | 'replace'>(null);
  useEffect(() => { findModeRef.current = findMode; }, [findMode]);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const editorRef = useRef<any>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const hasRestoredScrollRef = useRef(false);
  const onScrollTopChangeRef = useRef(onScrollTopChange);
  useEffect(() => { onScrollTopChangeRef.current = onScrollTopChange; }, [onScrollTopChange]);
  const onHeadingsChangeRef = useRef(onHeadingsChange);
  useEffect(() => { onHeadingsChangeRef.current = onHeadingsChange; }, [onHeadingsChange]);
  const headingsDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [activeHeadingId, setActiveHeadingId] = useState<string | null>(null);
  const tocHeadingsRef = useRef(tocHeadings);
  useEffect(() => { tocHeadingsRef.current = tocHeadings; }, [tocHeadings]);
  const tocNavRef = useRef<HTMLElement>(null);
  const headingElsCacheRef = useRef<HTMLElement[] | null>(null);
  useEffect(() => { headingElsCacheRef.current = null; }, [tocHeadings]);
  const tocScrollRafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!activeHeadingId || !tocNavRef.current) return;
    const nav = tocNavRef.current;
    const activeBtn = nav.querySelector<HTMLElement>('.toc-item-active');
    if (!activeBtn) return;
    const navRect = nav.getBoundingClientRect();
    const btnRect = activeBtn.getBoundingClientRect();
    const btnAbsoluteTop = btnRect.top - navRect.top + nav.scrollTop;
    nav.scrollTo({
      top: btnAbsoluteTop - nav.clientHeight / 2 + activeBtn.clientHeight / 2,
      behavior: 'smooth',
    });
  }, [activeHeadingId]);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const handleScroll = () => {
      if (tocScrollRafRef.current !== null) return;
      tocScrollRafRef.current = requestAnimationFrame(() => {
        tocScrollRafRef.current = null;
        if (!headingElsCacheRef.current) {
          headingElsCacheRef.current = Array.from(
            container.querySelectorAll<HTMLElement>(
              '.tiptap-editor h1,.tiptap-editor h2,.tiptap-editor h3,.tiptap-editor h4,.tiptap-editor h5'
            )
          );
        }
        const containerTop = container.getBoundingClientRect().top;
        let activeEl: HTMLElement | null = null;
        for (const el of headingElsCacheRef.current) {
          if (el.getBoundingClientRect().top - containerTop <= 64) {
            activeEl = el;
          } else {
            break;
          }
        }
        if (activeEl) {
          const text = activeEl.textContent?.trim() ?? '';
          const level = parseInt(activeEl.tagName[1]);
          const match = tocHeadingsRef.current.find(
            h => h.level === level && h.text.trim() === text
          );
          setActiveHeadingId(match?.id ?? null);
        } else {
          setActiveHeadingId(null);
        }
      });
    };
    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      container.removeEventListener('scroll', handleScroll);
      if (tocScrollRafRef.current !== null) cancelAnimationFrame(tocScrollRafRef.current);
    };
  }, []); // attach once, reads tocHeadingsRef via refs

  const insertImageFiles = useCallback(async (inputFiles: FileList | File[]) => {
    const activeEditor = editorRef.current;
    if (!activeEditor) return;
    const files = Array.from(inputFiles).filter(f => f.type.startsWith('image/'));
    if (!files.length) return;
    for (const file of files) {
      const src = await readFileAsDataUrl(file);
      activeEditor.chain().focus().insertContent([
        { type: 'floatingImage', attrs: { src, alt: file.name, title: file.name, width: 56 } },
        { type: 'paragraph' },
      ]).run();
    }
  }, []);

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if ((event.target as HTMLElement | null)?.closest('.context-menu')) return;
      setContextMenu(null);
    };
    document.addEventListener('pointerdown', handlePointerDown, true);
    return () => document.removeEventListener('pointerdown', handlePointerDown, true);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) {
        e.preventDefault();
        if (findModeRef.current) {
          setFindFocusTrigger(prev => prev + 1);
        } else {
          setFindMode('find');
        }
      }
      if ((e.ctrlKey || e.metaKey) && (e.key === 'h' || e.key === 'H')) {
        e.preventDefault();
        if (findModeRef.current === 'replace') {
          setFindFocusTrigger(prev => prev + 1);
        } else {
          setFindMode('replace');
        }
      }
      if (e.key === 'Escape' && findModeRef.current) { e.stopPropagation(); setFindMode(null); }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    const menuWidth = 220, menuHeight = 260, padding = 12;
    const x = Math.min(e.clientX, window.innerWidth - menuWidth - padding);
    const y = Math.min(e.clientY, window.innerHeight - menuHeight - padding);
    setContextMenu({ x: Math.max(padding, x), y: Math.max(padding, y) });
  };

  const editor = useEditor({
    extensions: [
      StarterKit,
      FloatingImage,
      TextStyle,
      Color,
      FontFamily.configure({ types: ['textStyle'] }),
      FontSize,
      Underline,
      Highlight.configure({ multicolor: true }),
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Link.configure({ openOnClick: false }),
      Subscript,
      Superscript,
      SearchHighlight,
    ],
    content: initialContent,
    onCreate: ({ editor }) => {
      editorRef.current = editor;
      onEditorReady?.(() => editorRef.current!.getHTML());
      onHeadingsChangeRef.current?.(extractHeadings(editor));
    },
    onUpdate: ({ editor }) => {
      onChange?.(editor.getHTML());
      if (headingsDebounceRef.current) clearTimeout(headingsDebounceRef.current);
      headingsDebounceRef.current = setTimeout(() => {
        onHeadingsChangeRef.current?.(extractHeadings(editor));
      }, 400);
    },
    editorProps: {
      attributes: {
        class: 'prose prose-sm sm:prose-base max-w-none focus:outline-none tiptap-editor',
        spellcheck: 'false',
      },
      handlePaste: (_view, event) => {
        const files = Array.from(event.clipboardData?.files || []).filter(f => f.type.startsWith('image/'));
        if (!files.length) return false;
        event.preventDefault();
        void insertImageFiles(files);
        return true;
      },
      handleDrop: (_view, event) => {
        const files = Array.from(event.dataTransfer?.files || []).filter(f => f.type.startsWith('image/'));
        if (!files.length) return false;
        event.preventDefault();
        void insertImageFiles(files);
        return true;
      },
    },
  });

  useEffect(() => { if (editor) editorRef.current = editor; }, [editor]);

  useEffect(() => {
    if (editor && initialContent !== editor.getHTML() && !editor.isFocused && editor.isEmpty) {
      editor.commands.setContent(initialContent);
    }
  }, [initialContent, editor]);

  useEffect(() => {
    if (hasRestoredScrollRef.current || !scrollContainerRef.current || !editor || !initialScrollTop) return;
    hasRestoredScrollRef.current = true;
    requestAnimationFrame(() => {
      if (scrollContainerRef.current) scrollContainerRef.current.scrollTop = initialScrollTop;
    });
  }, [editor, initialScrollTop]);

  return (
    <div className="editor-shell flex flex-1 min-h-0 w-full flex-col relative" onContextMenu={handleContextMenu}>
      <MenuBar
        editor={editor}
        onInsertImages={insertImageFiles}
        showFindReplace={findMode !== null}
        onToggleFindReplace={() => setFindMode(p => p ? null : 'find')}
      />
      {findMode && editor && (
        <FindReplacePanel editor={editor} onClose={() => setFindMode(null)} initialMode={findMode} focusTrigger={findFocusTrigger} />
      )}
      <div
        ref={scrollContainerRef}
        className="editor-page-container flex-1 overflow-y-auto"
        onScroll={() => {
          if (scrollContainerRef.current) {
            onScrollTopChangeRef.current?.(scrollContainerRef.current.scrollTop);
          }
        }}
      >
        <div className="editor-page-outer">
          {/* Left TOC column — lives inside the gray area */}
          <div className="editor-toc-col" style={{ width: isTocOpen ? 260 : 44 }}>
            <div className="editor-toc-sticky">
              {!isTocOpen ? (
                <button className="editor-toc-btn" onClick={onTocToggle} title="Apri indice">
                  <Menu className="w-4 h-4" />
                </button>
              ) : (
                <>
                  <div className="editor-toc-header">
                    <span>Indice</span>
                    <button className="toc-left-close" onClick={onTocToggle} title="Chiudi">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <nav className="editor-toc-nav" ref={tocNavRef}>
                    {tocHeadings.length === 0 ? (
                      <p className="toc-empty">Nessun titolo</p>
                    ) : (
                      tocHeadings.map(h => (
                        <button
                          key={h.id}
                          className={`toc-item toc-item-h${h.level}${activeHeadingId === h.id ? ' toc-item-active' : ''}`}
                          style={{ paddingLeft: `${(h.level - 1) * 12 + 14}px` }}
                          onClick={() => onScrollToHeading?.(h)}
                          title={h.text}
                        >
                          {h.text}
                        </button>
                      ))
                    )}
                  </nav>
                </>
              )}
            </div>
          </div>
          {/* White paper — centering wrapper takes all remaining space */}
          <div className="editor-page-center">
            <div className="editor-page">
              <EditorContent editor={editor} />
            </div>
          </div>
          {/* Symmetric right spacer so the paper stays centered */}
          <div className="editor-toc-spacer" style={{ width: isTocOpen ? 260 : 44 }} />
        </div>
      </div>
      {editor && <WordCount editor={editor} />}

      {contextMenu && createPortal(
        <div
          className="context-menu fixed z-50 py-1 text-sm"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={e => { e.stopPropagation(); setContextMenu(null); }}
        >
          <button className="context-menu-item" onClick={async () => {
            try {
              const { from, to } = editor!.state.selection;
              const text = editor!.state.doc.textBetween(from, to, '\n');
              await navigator.clipboard.writeText(text);
              editor!.chain().focus().deleteSelection().run();
            } catch (_) { console.error('Clipboard permission denied'); }
          }}>
            <Scissors className="h-4 w-4" /> Taglia
          </button>
          <button className="context-menu-item" onClick={async () => {
            try {
              const { from, to } = editor!.state.selection;
              const text = editor!.state.doc.textBetween(from, to, '\n');
              await navigator.clipboard.writeText(text);
              editor!.chain().focus().run();
            } catch (_) { console.error('Clipboard permission denied'); }
          }}>
            <Copy className="h-4 w-4" /> Copia
          </button>
          <button className="context-menu-item" onClick={async () => {
            try {
              const text = await navigator.clipboard.readText();
              editor?.commands.insertContent(text);
            } catch (_) { console.error('Clipboard permission denied'); }
          }}>
            <Clipboard className="h-4 w-4" /> Incolla
          </button>
          <div className="editor-separator mx-3 my-1 w-auto" />
          <button className="context-menu-item" onClick={() => { editor?.chain().focus().toggleBold().run(); setContextMenu(null); }}>
            <Bold className="h-4 w-4" /> Grassetto
          </button>
          <button className="context-menu-item" onClick={() => { editor?.chain().focus().toggleItalic().run(); setContextMenu(null); }}>
            <Italic className="h-4 w-4" /> Corsivo
          </button>
          <button className="context-menu-item" onClick={() => { editor?.chain().focus().toggleUnderline().run(); setContextMenu(null); }}>
            <UnderlineIcon className="h-4 w-4" /> Sottolineato
          </button>
          <button className="context-menu-item" onClick={() => { imageInputRef.current?.click(); }}>
            <ImagePlus className="h-4 w-4" /> Inserisci immagine
          </button>
        </div>
      , document.body)}

      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={event => {
          if (event.target.files?.length) void insertImageFiles(event.target.files);
          event.currentTarget.value = '';
          setContextMenu(null);
        }}
      />
    </div>
  );
}
