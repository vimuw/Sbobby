import React, { useEffect } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Bold, Clipboard, Copy, FileText, Heading1, Heading2, Heading3, Heading4, Heading5, Italic, List, ListOrdered, Printer, Quote, Redo, Scissors, Undo } from 'lucide-react';

interface RichTextEditorProps {
  initialContent: string;
  onChange: (html: string) => void;
}

const MenuBar = ({ editor }: { editor: any }) => {
  const [, forceUpdate] = React.useState({});

  React.useEffect(() => {
    if (!editor) return;
    const handleTransaction = () => forceUpdate({});
    editor.on('transaction', handleTransaction);
    return () => { editor.off('transaction', handleTransaction); };
  }, [editor]);

  if (!editor) return null;

  const toggleHeading = (level: 1 | 2 | 3 | 4 | 5) => {
    editor.chain().focus().toggleHeading({ level }).run();
  };

  const handlePrint = () => {
    const html = editor.getHTML();
    const printWindow = document.createElement('iframe');
    printWindow.style.position = 'fixed';
    printWindow.style.top = '5vh';
    printWindow.style.left = '5vw';
    printWindow.style.width = '90vw';
    printWindow.style.height = '90vh';
    printWindow.style.opacity = '0';
    printWindow.style.pointerEvents = 'none';
    printWindow.style.zIndex = '-1';
    document.body.appendChild(printWindow);

    const styleLinks = Array.from(document.querySelectorAll('link[rel="stylesheet"], style')).map(el => el.outerHTML).join('\n');
    const doc = printWindow.contentWindow?.document;

    if (!doc) return;

    doc.open();
    doc.write(`
      <html>
        <head>
          <title>Sbobina</title>
          <meta charset="utf-8">
          ${styleLinks}
          <style>
            body { padding: 40px !important; background: white !important; color: black !important; }
            @media print { body { padding: 0 !important; } }
          </style>
        </head>
        <body>
          <div class="prose prose-sm sm:prose-base max-w-none tiptap-editor">
            ${html}
          </div>
          <script>
            window.onload = () => {
              setTimeout(() => {
                window.print();
                setTimeout(() => {
                  window.parent.document.body.removeChild(window.frameElement);
                }, 1000);
              }, 750);
            };
          </script>
        </body>
      </html>
    `);
    doc.close();
  };

  const handleExportWord = async () => {
    const html = editor.getHTML();
    const docxTemplate = `
      <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
      <head><meta charset='utf-8'><title>Esporta Sbobina</title></head><body>
      ${html}
      </body></html>
    `;

    if (window.pywebview?.api?.export_docx) {
      const res = await window.pywebview.api.export_docx('Sbobina.doc', docxTemplate);
      if (!res.ok && res.error !== "Annullato dall'utente") {
        alert(`Errore salvataggio Word: ${res.error}`);
      }
    } else {
      const blob = new Blob(['\ufeff', docxTemplate], { type: 'application/msword;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'Sbobina.doc';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
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
      <div className="editor-separator" />
      <button type="button" onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()} className="editor-button" title="Annulla">
        <Undo className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()} className="editor-button" title="Ripeti">
        <Redo className="h-4 w-4" />
      </button>

      <div className="ml-auto flex items-center gap-2">
        <button type="button" onClick={handleExportWord} className="editor-button" title="Esporta in Word (.doc)">
          <FileText className="h-4 w-4" />
        </button>
        <button type="button" onClick={handlePrint} className="editor-button" title="Stampa / Esporta in PDF">
          <Printer className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};

export function RichTextEditor({ initialContent, onChange }: RichTextEditorProps) {
  const [contextMenu, setContextMenu] = React.useState<{ x: number; y: number } | null>(null);

  React.useEffect(() => {
    const handleClickDefault = () => setContextMenu(null);
    document.addEventListener('click', handleClickDefault);
    return () => document.removeEventListener('click', handleClickDefault);
  }, []);

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    setContextMenu({ x: e.pageX, y: e.pageY });
  };

  const editor = useEditor({
    extensions: [StarterKit],
    content: initialContent,
    editorProps: {
      attributes: {
        class: 'prose prose-sm sm:prose-base max-w-none focus:outline-none min-h-[500px] p-6 tiptap-editor',
        spellcheck: 'false',
      },
    },
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
    },
  });

  useEffect(() => {
    if (editor && initialContent !== editor.getHTML() && !editor.isFocused) {
      if (editor.isEmpty) {
        editor.commands.setContent(initialContent);
      }
    }
  }, [initialContent, editor]);

  return (
    <div className="editor-shell flex flex-1 min-h-0 w-full flex-col relative" onContextMenu={handleContextMenu}>
      <MenuBar editor={editor} />
      <div className="flex-1 overflow-y-auto">
        <EditorContent editor={editor} />
      </div>

      {contextMenu && (
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
          <button className="context-menu-item" onClick={() => { editor?.chain().focus().toggleHeading({ level: 1 }).run(); }}>
            <Heading1 className="h-4 w-4" /> Titolo 1
          </button>
          <button className="context-menu-item" onClick={() => { editor?.chain().focus().toggleHeading({ level: 2 }).run(); }}>
            <Heading2 className="h-4 w-4" /> Titolo 2
          </button>
        </div>
      )}
    </div>
  );
}
