import { describe, expect, it } from 'vitest';
import { normalizePreviewHtmlContent, ALLOWED_STYLE_PROPS, EDITOR_IMAGE_ALLOWED_DATA_ATTRS } from './previewHtml';

describe('normalizePreviewHtmlContent', () => {
  it('returns empty string for empty input', () => {
    const result = normalizePreviewHtmlContent('');
    expect(result).toBe('');
  });

  it('strips disallowed data-* attributes', () => {
    const html = '<p data-bad-attr="x">hello</p>';
    const result = normalizePreviewHtmlContent(html);
    expect(result).not.toContain('data-bad-attr');
    expect(result).toContain('hello');
  });

  it('strips align attribute', () => {
    const html = '<p align="center">text</p>';
    const result = normalizePreviewHtmlContent(html);
    expect(result).not.toContain('align="center"');
  });

  it('preserves allowed style properties', () => {
    const html = '<p style="color: red; font-size: 14px;">styled</p>';
    const result = normalizePreviewHtmlContent(html);
    expect(result).toContain('color');
    expect(result).toContain('font-size');
  });

  it('strips disallowed style properties', () => {
    const html = '<p style="margin: 10px; padding: 5px;">text</p>';
    const result = normalizePreviewHtmlContent(html);
    expect(result).not.toContain('margin');
    expect(result).not.toContain('padding');
  });

  it('removes style attribute entirely when no allowed props remain', () => {
    const html = '<p style="margin: 10px;">text</p>';
    const result = normalizePreviewHtmlContent(html);
    expect(result).not.toContain('style=');
  });

  it('preserves editor image container data-* attributes', () => {
    const html = '<div data-editor-image data-width="60" data-bad="x"><img src="img.png" /></div>';
    const result = normalizePreviewHtmlContent(html);
    expect(result).toContain('data-editor-image');
    expect(result).toContain('data-width');
    expect(result).not.toContain('data-bad');
  });

  it('strips class from editor image containers', () => {
    const html = '<div data-editor-image class="foo"><img src="img.png" /></div>';
    const result = normalizePreviewHtmlContent(html);
    expect(result).not.toContain('class="foo"');
  });

  it('strips class from img inside editor image container', () => {
    const html = '<div data-editor-image><img src="img.png" class="bar" data-extra="x" /></div>';
    const result = normalizePreviewHtmlContent(html);
    expect(result).not.toContain('class="bar"');
    expect(result).not.toContain('data-extra');
    expect(result).toContain('src="img.png"');
  });

  it('handles nested elements', () => {
    const html = '<div data-foo="x"><span data-bar="y">text</span></div>';
    const result = normalizePreviewHtmlContent(html);
    expect(result).not.toContain('data-foo');
    expect(result).not.toContain('data-bar');
    expect(result).toContain('text');
  });

  it('exports ALLOWED_STYLE_PROPS with expected members', () => {
    expect(ALLOWED_STYLE_PROPS.has('color')).toBe(true);
    expect(ALLOWED_STYLE_PROPS.has('font-size')).toBe(true);
    expect(ALLOWED_STYLE_PROPS.has('margin')).toBe(false);
  });

  it('exports EDITOR_IMAGE_ALLOWED_DATA_ATTRS with expected members', () => {
    expect(EDITOR_IMAGE_ALLOWED_DATA_ATTRS.has('data-editor-image')).toBe(true);
    expect(EDITOR_IMAGE_ALLOWED_DATA_ATTRS.has('data-width')).toBe(true);
    expect(EDITOR_IMAGE_ALLOWED_DATA_ATTRS.has('data-foo')).toBe(false);
  });
});
