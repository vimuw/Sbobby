import { describe, expect, it } from 'vitest';

import { initialProcessingState, processingReducer, type FileItem } from './appState';


function makeFile(overrides: Partial<FileItem> = {}): FileItem {
  return {
    id: 'file-1',
    name: 'lesson.mp3',
    size: 1024,
    duration: 60,
    status: 'queued',
    progress: 0,
    phase: 0,
    ...overrides,
  };
}


describe('processingReducer', () => {
  it('adds and reorders queued files', () => {
    const first = makeFile({ id: 'a', name: 'a.mp3' });
    const second = makeFile({ id: 'b', name: 'b.mp3' });

    let state = processingReducer(initialProcessingState, { type: 'queue/add', files: [first, second] });
    state = processingReducer(state, { type: 'queue/reorder', fromIndex: 1, toIndex: 0 });

    expect(state.files.map(file => file.id)).toEqual(['b', 'a']);
  });

  it('marks current file as processing and completes it', () => {
    const file = makeFile({ id: 'abc' });
    let state = processingReducer(initialProcessingState, { type: 'queue/add', files: [file] });

    state = processingReducer(state, {
      type: 'bridge/set_current_file',
      data: { id: 'abc', index: 0, total: 1 },
    });
    expect(state.appState).toBe('processing');
    expect(state.files[0].status).toBe('processing');

    state = processingReducer(state, {
      type: 'bridge/file_done',
      data: { id: 'abc', index: 0, output_html: 'out.html', output_dir: 'dir' },
    });
    expect(state.files[0].status).toBe('done');
    expect(state.files[0].outputHtml).toBe('out.html');
  });

  it('resets error files to queued on retry_failed', () => {
    const failed = makeFile({ id: 'f1', status: 'error', progress: 0, phase: 0, errorText: 'timeout' });
    const done = makeFile({ id: 'f2', status: 'done', progress: 100, phase: 3 });
    const queued = makeFile({ id: 'f3', status: 'queued' });
    const state = processingReducer(
      { ...initialProcessingState, files: [failed, done, queued] },
      { type: 'queue/retry_failed' },
    );
    expect(state.files[0].status).toBe('queued');
    expect(state.files[0].progress).toBe(0);
    expect(state.files[0].phase).toBe(0);
    expect(state.files[0].errorText).toBeUndefined();
    expect(state.files[1].status).toBe('done');
    expect(state.files[2].status).toBe('queued');
  });

  it('resets processing files to queued on cancelled batch completion', () => {
    const file = makeFile({ status: 'processing', progress: 50, phase: 1 });
    const state = processingReducer(
      { ...initialProcessingState, appState: 'processing', currentPhase: 'Fase 1', files: [file] },
      { type: 'bridge/process_done', data: { cancelled: true, total: 1 } },
    );

    expect(state.appState).toBe('idle');
    expect(state.currentPhase).toBe('');
    expect(state.files[0].status).toBe('queued');
    expect(state.files[0].progress).toBe(0);
  });
});
