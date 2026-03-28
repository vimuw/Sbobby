import React, { useCallback, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Color } from '@tiptap/extension-color';
import { TextStyle } from '@tiptap/extension-text-style';
import { Bold, ChevronDown, Clipboard, Copy, Heading1, Heading2, Heading3, Heading4, Heading5, ImagePlus, Italic, List, ListOrdered, Quote, Redo, Scissors, Undo } from 'lucide-react';
import { FloatingImage } from './FloatingImage';

interface RichTextEditorProps {
  initialContent: string;
  onChange: (html: string) => void;
  initialScrollTop?: number;
  onScrollTopChange?: (scrollTop: number) => void;
  onHeadingsChange?: (
    headings: { id: string; level: number; text: string }[],
    scrollTo: (index: number) => void
  ) => void;
}

const COLOR_PALETTE: string[][] = [
  ['#000000', '#434343', '#666666', '#999999', '#b7b7b7', '#cccccc', '#d9d9d9', '#ffffff'],
  ['#ff0000', '#ff4500', '#ff9900', '#ffff00', '#00ff00', '#00ffff', '#4a86e8', '#9900ff'],
  ['#f4cccc', '#fce5cd', '#fff2cc', '#d9ead3', '#c9daf8', '#cfe2f3', '#d9d2e9', '#ead1dc'],
  ['#ea9999', '#f9cb9c', '#ffe599', '#b6d7a8', '#a4c2f4', '#9fc5e8', '#b4a7d6', '#d5a6bd'],
  ['#e06666', '#f6b26b', '#ffd966', '#93c47d', '#6d9eeb', '#6fa8dc', '#8e7cc3', '#c27ba0'],
  ['#cc0000', '#e69138', '#f1c232', '#6aa84f', '#3c78d8', '#3d85c8', '#674ea7', '#a64d79'],
  ['#990000', '#b45f06', '#bf9000', '#38761d', '#1155cc', '#0b5394', '#20124d', '#4c1130'],
];

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

function extractHeadings(editor: any): { id: string; level: number; text: string }[] {
  const json = editor.getJSON();
  const headings: { id: string; level: number; text: string }[] = [];
  let hi = 0;
  json.content?.forEach((node: any) => {
    if (node.type === 'heading') {
      const text = node.content?.map((n: any) => n.text ?? '').join('') ?? '';
      headings.push({ id: `h-${hi++}`, level: node.attrs?.level ?? 2, text });
    }
  });
  return headings;
}

const readFileAsDataUrl = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('Lettura immagine fallita.'));
    reader.readAsDataURL(file);
  });

const menuBarStateKey = (editor: any): string => [
  editor.isActive('bold'),
  editor.isActive('italic'),
  editor.isActive('heading', { level: 1 }),
  editor.isActive('heading', { level: 2 }),
  editor.isActive('heading', { level: 3 }),
  editor.isActive('heading', { level: 4 }),
  editor.isActive('heading', { level: 5 }),
  editor.isActive('bulletList'),
  editor.isActive('orderedList'),
  editor.isActive('blockquote'),
  editor.can().undo(),
  editor.can().redo(),
  editor.getAttributes('textStyle').color ?? '',
].join('|');

const MenuBar = ({ editor, onInsertImages }: { editor: any; onInsertImages: (files: FileList | File[]) => void }) => {
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

  const toggleHeading = (level: 1 | 2 | 3 | 4 | 5) => {
    editor.chain().focus().toggleHeading({ level }).run();
  };

  const btnClass = (isActive: boolean) => `editor-button ${isActive ? 'is-active' : ''}`;

  return (
    <div className="editor-toolbar">
      <button type="button" onClick={() => editor.chain().focus().toggleBold().run()} className={btnClass(editor.isActive('bold'))} title="Grassetto">
        <Bold className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().toggleItalic().run()} className={btnClass(editor.isActive('italic'))} title="Corsivo">
        <Italic className="h-4 w-4" />
      </button>
      <ColorPickerButton editor={editor} />
      <div className="editor-separator" />
      <button type="button" onClick={() => toggleHeading(1)} className={btnClass(editor.isActive('heading', { level: 1 }))} title="Titolo 1">
        <Heading1 className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => toggleHeading(2)} className={btnClass(editor.isActive('heading', { level: 2 }))} title="Titolo 2">
        <Heading2 className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => toggleHeading(3)} className={btnClass(editor.isActive('heading', { level: 3 }))} title="Titolo 3">
        <Heading3 className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => toggleHeading(4)} className={btnClass(editor.isActive('heading', { level: 4 }))} title="Titolo 4">
        <Heading4 className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => toggleHeading(5)} className={btnClass(editor.isActive('heading', { level: 5 }))} title="Titolo 5">
        <Heading5 className="h-4 w-4" />
      </button>
      <div className="editor-separator" />
      <button type="button" onClick={() => editor.chain().focus().toggleBulletList().run()} className={btnClass(editor.isActive('bulletList'))} title="Elenco puntato">
        <List className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().toggleOrderedList().run()} className={btnClass(editor.isActive('orderedList'))} title="Elenco numerato">
        <ListOrdered className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().toggleBlockquote().run()} className={btnClass(editor.isActive('blockquote'))} title="Citazione">
        <Quote className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => imageInputRef.current?.click()} className="editor-button" title="Inserisci immagine">
        <ImagePlus className="h-4 w-4" />
      </button>
      <div className="editor-separator" />
      <button type="button" onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()} className="editor-button" title="Annulla">
        <Undo className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()} className="editor-button" title="Ripeti">
        <Redo className="h-4 w-4" />
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

export function RichTextEditor({ initialContent, onChange, initialScrollTop, onScrollTopChange, onHeadingsChange }: RichTextEditorProps) {
  const [contextMenu, setContextMenu] = React.useState<{ x: number; y: number } | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const editorRef = useRef<any>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const hasRestoredScrollRef = useRef(false);
  const onScrollTopChangeRef = useRef(onScrollTopChange);
  useEffect(() => { onScrollTopChangeRef.current = onScrollTopChange; }, [onScrollTopChange]);

  const onHeadingsChangeRef = useRef(onHeadingsChange);
  useEffect(() => { onHeadingsChangeRef.current = onHeadingsChange; }, [onHeadingsChange]);

  const scrollToHeading = useCallback((index: number) => {
    if (!scrollContainerRef.current) return;
    const els = scrollContainerRef.current.querySelectorAll('h1, h2, h3, h4, h5');
    const el = els[index] as HTMLElement | undefined;
    if (!el) return;
    const container = scrollContainerRef.current;
    const elTop = el.getBoundingClientRect().top;
    const containerTop = container.getBoundingClientRect().top;
    container.scrollBy({ top: elTop - containerTop - 16, behavior: 'smooth' });
  }, []);

  const insertImageFiles = useCallback(async (inputFiles: FileList | File[]) => {
    const activeEditor = editorRef.current;
    if (!activeEditor) return;

    const files = Array.from(inputFiles).filter(file => file.type.startsWith('image/'));
    if (!files.length) return;

    for (const file of files) {
      const src = await readFileAsDataUrl(file);
      activeEditor
        .chain()
        .focus()
        .insertContent([
          {
            type: 'floatingImage',
            attrs: {
              src,
              alt: file.name,
              title: file.name,
              width: 56,
            },
          },
          {
            type: 'paragraph',
          },
        ])
        .run();
    }
  }, []);

  React.useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if ((event.target as HTMLElement | null)?.closest('.context-menu')) {
        return;
      }
      setContextMenu(null);
    };

    document.addEventListener('pointerdown', handlePointerDown, true);
    return () => document.removeEventListener('pointerdown', handlePointerDown, true);
  }, []);

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    const menuWidth = 220;
    const menuHeight = 320;
    const padding = 12;
    const x = Math.min(e.clientX, window.innerWidth - menuWidth - padding);
    const y = Math.min(e.clientY, window.innerHeight - menuHeight - padding);
    setContextMenu({
      x: Math.max(padding, x),
      y: Math.max(padding, y),
    });
  };

  const editor = useEditor({
    extensions: [StarterKit, FloatingImage, TextStyle, Color],
    content: initialContent,
    onCreate: ({ editor }) => {
      editorRef.current = editor;
      onHeadingsChangeRef.current?.(extractHeadings(editor), scrollToHeading);
    },
    editorProps: {
      attributes: {
        class: 'prose prose-sm sm:prose-base max-w-none focus:outline-none min-h-[500px] p-6 tiptap-editor',
        spellcheck: 'false',
      },
      handlePaste: (_view, event) => {
        const files = Array.from(event.clipboardData?.files || []).filter(file => file.type.startsWith('image/'));
        if (!files.length) return false;
        event.preventDefault();
        void insertImageFiles(files);
        return true;
      },
      handleDrop: (_view, event) => {
        const files = Array.from(event.dataTransfer?.files || []).filter(file => file.type.startsWith('image/'));
        if (!files.length) return false;
        event.preventDefault();
        void insertImageFiles(files);
        return true;
      },
    },
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
      onHeadingsChangeRef.current?.(extractHeadings(editor), scrollToHeading);
    },
  });

  useEffect(() => {
    if (editor) {
      editorRef.current = editor;
    }
  }, [editor]);

  useEffect(() => {
    if (editor && initialContent !== editor.getHTML() && !editor.isFocused) {
      if (editor.isEmpty) {
        editor.commands.setContent(initialContent);
      }
    }
  }, [initialContent, editor]);

  useEffect(() => {
    if (hasRestoredScrollRef.current || !scrollContainerRef.current || !editor || !initialScrollTop) return;
    hasRestoredScrollRef.current = true;
    requestAnimationFrame(() => {
      if (scrollContainerRef.current) {
        scrollContainerRef.current.scrollTop = initialScrollTop;
      }
    });
  }, [editor, initialScrollTop]);

  return (
    <div className="editor-shell flex flex-1 min-h-0 w-full flex-col relative" onContextMenu={handleContextMenu}>
      <MenuBar editor={editor} onInsertImages={insertImageFiles} />
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto"
        onScroll={() => {
          if (scrollContainerRef.current) {
            onScrollTopChangeRef.current?.(scrollContainerRef.current.scrollTop);
          }
        }}
      >
        <EditorContent editor={editor} />
      </div>

      {contextMenu && createPortal(
        <div
          className="context-menu fixed z-50 py-1 text-sm"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={e => {
            e.stopPropagation();
            setContextMenu(null);
          }}
        >
          <button className="context-menu-item" onClick={() => { document.execCommand('cut'); editor?.chain().focus().run(); }}>
            <Scissors className="h-4 w-4" /> Taglia
          </button>
          <button className="context-menu-item" onClick={() => { document.execCommand('copy'); editor?.chain().focus().run(); }}>
            <Copy className="h-4 w-4" /> Copia
          </button>
          <button className="context-menu-item" onClick={async () => {
            try {
              const text = await navigator.clipboard.readText();
              editor?.commands.insertContent(text);
            } catch (_) {
              console.error('Clipboard permission denied');
            }
          }}>
            <Clipboard className="h-4 w-4" /> Incolla
          </button>
          <div className="editor-separator mx-3 my-1 w-auto" />
          <button className="context-menu-item" onClick={() => { editor?.chain().focus().toggleBold().run(); }}>
            <Bold className="h-4 w-4" /> Grassetto
          </button>
          <button className="context-menu-item" onClick={() => { editor?.chain().focus().toggleItalic().run(); }}>
            <Italic className="h-4 w-4" /> Corsivo
          </button>
          <button className="context-menu-item" onClick={() => imageInputRef.current?.click()}>
            <ImagePlus className="h-4 w-4" /> Inserisci immagine
          </button>
          <button className="context-menu-item" onClick={() => { editor?.chain().focus().toggleHeading({ level: 1 }).run(); }}>
            <Heading1 className="h-4 w-4" /> Titolo 1
          </button>
          <button className="context-menu-item" onClick={() => { editor?.chain().focus().toggleHeading({ level: 2 }).run(); }}>
            <Heading2 className="h-4 w-4" /> Titolo 2
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
          if (event.target.files?.length) {
            void insertImageFiles(event.target.files);
          }
          event.currentTarget.value = '';
          setContextMenu(null);
        }}
      />
    </div>
  );
}
