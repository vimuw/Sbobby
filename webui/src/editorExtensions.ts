import { Extension, type Editor as TiptapEditor, type JSONContent } from '@tiptap/core';
import type { Node as ProseMirrorNode } from '@tiptap/pm/model';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet, type EditorView } from '@tiptap/pm/view';

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    searchHighlight: {
      setSearchTerm: (term: string, currentIndex?: number, matchCase?: boolean) => ReturnType;
    };
  }
}

export interface Heading {
  id: string;
  level: number;
  text: string;
}

export const extractHeadings = (editor: TiptapEditor): Heading[] => {
  const json = editor.getJSON() as JSONContent;
  const result: Heading[] = [];
  json.content?.forEach((node: JSONContent, idx: number) => {
    if (node.type === 'heading') {
      const text = node.content?.map((n: JSONContent) => n.text ?? '').join('') ?? '';
      if (text.trim()) result.push({ id: `h-${idx}`, level: node.attrs?.level ?? 2, text });
    }
  });
  return result;
};

interface SearchHighlightPluginState {
  searchTerm: string;
  currentIndex: number;
  matchCase: boolean;
  decorations: DecorationSet;
}

const searchHighlightKey = new PluginKey<SearchHighlightPluginState>('searchHighlight');

export const SearchHighlight = Extension.create({
  name: 'searchHighlight',

  addCommands() {
    return {
      setSearchTerm:
        (term: string, currentIndex = -1, matchCase = false) =>
        ({ view }: { view: EditorView }) => {
          view.dispatch(
            view.state.tr.setMeta(searchHighlightKey, { term, currentIndex, matchCase }),
          );
          return true;
        },
    };
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

            newState.doc.descendants((node: ProseMirrorNode, pos: number) => {
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

export const FontSize = Extension.create({
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
