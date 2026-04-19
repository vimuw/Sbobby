import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { type Editor as TiptapEditor } from '@tiptap/core';
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
import {
  Bold, Clipboard, Copy, ImagePlus, Italic,
  Menu, RemoveFormatting, Scissors, Underline as UnderlineIcon, X,
} from 'lucide-react';
import { FloatingImage } from './FloatingImage';
import { type Heading, SearchHighlight, FontSize, extractHeadings } from './editorExtensions';
import { MenuBar } from './components/EditorToolbar';
import { FindReplacePanel } from './components/EditorFindReplace';
import { WordCount } from './components/EditorWordCount';
import { readFileAsDataUrl } from './components/EditorToolbarControls';

export type { Heading };

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

export function RichTextEditor({ initialContent, onChange, onEditorReady, initialScrollTop, onScrollTopChange, onHeadingsChange, isTocOpen = false, onTocToggle, tocHeadings = [], onScrollToHeading }: RichTextEditorProps) {
  const [contextMenu, setContextMenu] = React.useState<{ x: number; y: number } | null>(null);
  const [findMode, setFindMode] = useState<null | 'find' | 'replace'>(null);
  const [findFocusTrigger, setFindFocusTrigger] = useState(0);
  const findModeRef = useRef<null | 'find' | 'replace'>(null);
  useEffect(() => { findModeRef.current = findMode; }, [findMode]);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const editorRef = useRef<TiptapEditor | null>(null);
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
  const tocStickyRef = useRef<HTMLDivElement>(null);
  const headingElsCacheRef = useRef<HTMLElement[] | null>(null);
  useEffect(() => { headingElsCacheRef.current = null; }, [tocHeadings]);
  const tocScrollRafRef = useRef<number | null>(null);

  useEffect(() => {
    const container = scrollContainerRef.current;
    const sticky = tocStickyRef.current;
    if (!container || !sticky) return;
    const update = () => { sticky.style.height = `${Math.max(100, container.clientHeight - 60)}px`; };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!activeHeadingId || !tocNavRef.current) return;
    const nav = tocNavRef.current;
    const activeBtn = nav.querySelector<HTMLElement>('.toc-item-active');
    if (!activeBtn) return;
    const navRect = nav.getBoundingClientRect();
    const btnRect = activeBtn.getBoundingClientRect();
    if (btnRect.top < navRect.top) {
      nav.scrollTop += btnRect.top - navRect.top;
    } else if (btnRect.bottom > navRect.bottom) {
      nav.scrollTop += btnRect.bottom - navRect.bottom;
    }
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
      transformPastedHTML(html: string): string {
        const doc = new DOMParser().parseFromString(html, 'text/html');
        doc.body.querySelectorAll('[style]').forEach(el => {
          const s = (el as HTMLElement).style;
          s.removeProperty('color');
          s.removeProperty('background-color');
        });
        return doc.body.innerHTML;
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
            <div className="editor-toc-sticky" ref={tocStickyRef}>
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
          <button className="context-menu-item" onClick={() => { if (editor && !editor.state.selection.empty) { editor.chain().focus().unsetAllMarks().clearNodes().run(); } setContextMenu(null); }}>
            <RemoveFormatting className="h-4 w-4" /> Rimuovi formattazione
          </button>
          <div className="editor-separator mx-3 my-1 w-auto" />
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
