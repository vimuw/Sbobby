import React, { useRef } from 'react';
import { Node, mergeAttributes } from '@tiptap/core';
import { NodeViewWrapper, ReactNodeViewRenderer, type NodeViewProps } from '@tiptap/react';
import { Trash2 } from 'lucide-react';

const clampWidth = (value: unknown) => {
  const numeric = typeof value === 'number' ? value : Number.parseFloat(String(value ?? '56'));
  if (!Number.isFinite(numeric)) return 56;
  return Math.min(100, Math.max(28, Math.round(numeric)));
};

const buildWrapperReactStyle = (width: number): React.CSSProperties => ({
  width: `${width}%`,
  maxWidth: '100%',
  position: 'relative',
  display: 'block',
  margin: '12px auto 18px',
});

const buildWrapperStyle = (width: number) =>
  `width:${width}%;max-width:100%;position:relative;display:block;margin:12px auto 18px;`;

const buildImageStyle = () => 'display:block;width:100%;height:auto;border-radius:18px;';

const extractImageAttrs = (element: HTMLElement) => {
  const img = element.tagName.toLowerCase() === 'img' ? (element as HTMLImageElement) : element.querySelector('img');
  if (!img) {
    return false;
  }

  return {
    src: img.getAttribute('src') || '',
    alt: img.getAttribute('alt') || '',
    title: img.getAttribute('title') || '',
    width: clampWidth(element.getAttribute('data-width') || img.style.width || element.style.width || '56'),
  };
};

function FloatingImageView({ node, updateAttributes, deleteNode, selected }: NodeViewProps) {
  const anchorRef = useRef<HTMLDivElement | null>(null);
  const width = clampWidth(node.attrs.width);

  const startResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();

    const startX = event.clientX;
    const startWidth = width;
    const editorRoot = anchorRef.current?.closest('.tiptap-editor') as HTMLElement | null;
    const availableWidth = Math.max(editorRoot?.clientWidth || 0, 320);

    const move = (moveEvent: PointerEvent) => {
      const delta = moveEvent.clientX - startX;
      updateAttributes({ width: clampWidth(startWidth + (delta / availableWidth) * 100) });
    };

    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
    };

    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
  };

  return (
    <NodeViewWrapper
      as="div"
      ref={anchorRef}
      className={`editor-image-node ${selected ? 'is-selected' : ''}`}
      data-editor-image="true"
      data-width={width}
      style={buildWrapperReactStyle(width)}
    >
      <img
        src={String(node.attrs.src || '')}
        alt={String(node.attrs.alt || '')}
        title={String(node.attrs.title || '')}
        className="editor-image-asset"
        draggable="false"
      />
      <div className="editor-image-controls" contentEditable={false}>
        <div className="editor-image-toolbar">
          <button type="button" className="editor-image-action danger" onClick={deleteNode} aria-label="Rimuovi immagine">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
        <button
          type="button"
          className="editor-image-resize"
          onPointerDown={startResize}
          aria-label="Ridimensiona immagine"
        />
      </div>
    </NodeViewWrapper>
  );
}

export const FloatingImage = Node.create({
  name: 'floatingImage',
  group: 'block',
  atom: true,
  draggable: false,
  selectable: true,

  addAttributes() {
    return {
      src: { default: '' },
      alt: { default: '' },
      title: { default: '' },
      width: {
        default: 56,
        parseHTML: element => clampWidth((element as HTMLElement).getAttribute('data-width') || (element as HTMLElement).style.width),
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-editor-image]',
        getAttrs: element => extractImageAttrs(element as HTMLElement),
      },
      {
        tag: 'img[src]',
        getAttrs: element => extractImageAttrs(element as HTMLElement),
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    const width = clampWidth(HTMLAttributes.width);

    return [
      'div',
      mergeAttributes({
        'data-editor-image': 'true',
        'data-width': String(width),
        style: buildWrapperStyle(width),
      }),
      [
        'img',
        {
          src: HTMLAttributes.src,
          alt: HTMLAttributes.alt || '',
          title: HTMLAttributes.title || '',
          style: buildImageStyle(),
        },
      ],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(FloatingImageView);
  },
});
