import React, { useRef } from 'react';
import { type Editor as TiptapEditor } from '@tiptap/core';
import {
  AlignCenter, AlignJustify, AlignLeft, AlignRight,
  Bold, ImagePlus, Italic, List, ListOrdered, Quote, Redo,
  Search, Strikethrough, Subscript as SubIcon, Superscript as SupIcon,
  Underline as UnderlineIcon, Undo,
} from 'lucide-react';
import {
  ColorPickerButton, HighlightPickerButton, FontFamilySelect,
  FontSizeSelect, HeadingSelect, LinkButton,
} from './EditorToolbarControls';

const menuBarStateKey = (editor: TiptapEditor): string => [
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

export const MenuBar = ({
  editor,
  onInsertImages,
  showFindReplace,
  onToggleFindReplace,
}: {
  editor: TiptapEditor | null;
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
