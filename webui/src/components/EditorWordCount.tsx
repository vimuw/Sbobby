import React from 'react';
import { type Editor as TiptapEditor } from '@tiptap/core';

export const WordCount = ({ editor }: { editor: TiptapEditor }) => {
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
