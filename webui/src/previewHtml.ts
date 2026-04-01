export const EDITOR_IMAGE_ALLOWED_DATA_ATTRS = new Set(['data-editor-image', 'data-layout', 'data-align', 'data-width']);
export const ALLOWED_STYLE_PROPS = new Set(['font-size', 'color', 'font-family', 'background-color', 'text-align', 'font-weight', 'font-style', 'text-decoration']);

export const normalizePreviewHtmlContent = (content: string) => {
  const parsed = new DOMParser().parseFromString(`<body>${content || ''}</body>`, 'text/html');

  parsed.body.querySelectorAll('*').forEach(element => {
    const tag = element.tagName.toLowerCase();
    const isEditorImageContainer = tag === 'div' && element.hasAttribute('data-editor-image');
    const isEditorImageAsset = tag === 'img' && element.parentElement?.hasAttribute('data-editor-image');

    element.removeAttribute('align');

    if (!isEditorImageContainer && !isEditorImageAsset) {
      const htmlEl = element as HTMLElement;
      const allowedStyles = Array.from(htmlEl.style)
        .filter(prop => ALLOWED_STYLE_PROPS.has(prop))
        .map(prop => `${prop}: ${htmlEl.style.getPropertyValue(prop)}`)
        .join('; ');
      if (allowedStyles) {
        element.setAttribute('style', allowedStyles);
      } else {
        element.removeAttribute('style');
      }
      Array.from(element.attributes)
        .filter(attribute => attribute.name.startsWith('data-'))
        .forEach(attribute => element.removeAttribute(attribute.name));
      return;
    }

    if (isEditorImageContainer) {
      Array.from(element.attributes)
        .filter(attribute => attribute.name.startsWith('data-') && !EDITOR_IMAGE_ALLOWED_DATA_ATTRS.has(attribute.name))
        .forEach(attribute => element.removeAttribute(attribute.name));
      element.removeAttribute('class');
      return;
    }

    element.removeAttribute('class');
    Array.from(element.attributes)
      .filter(attribute => attribute.name.startsWith('data-'))
      .forEach(attribute => element.removeAttribute(attribute.name));
  });

  return parsed.body.innerHTML;
};
