import { describe, expect, it } from 'vitest';

import { getDoneFiles, getPendingFiles, initialProcessingState, processingReducer, type FileItem } from './appState';


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


describe('getPendingFiles / getDoneFiles selectors', () => {
  const queued = makeFile({ id: 'q', status: 'queued' });
  const processing = makeFile({ id: 'p', status: 'processing' });
  const error = makeFile({ id: 'e', status: 'error' });
  const done1 = makeFile({ id: 'd1', status: 'done', progress: 100, phase: 3, completedAt: 1000 });
  const done2 = makeFile({ id: 'd2', status: 'done', progress: 100, phase: 3, completedAt: 3000 });
  const done3 = makeFile({ id: 'd3', status: 'done', progress: 100, phase: 3, completedAt: 2000 });
  const mixed = [queued, processing, error, done1, done2, done3];

  it('getPendingFiles excludes all done files', () => {
    const result = getPendingFiles(mixed);
    expect(result.every(f => f.status !== 'done')).toBe(true);
    expect(result.map(f => f.id)).toEqual(['q', 'p', 'e']);
  });

  it('getPendingFiles returns an empty array when all files are done', () => {
    expect(getPendingFiles([done1, done2])).toEqual([]);
  });

  it('getDoneFiles includes only done files sorted by completedAt descending', () => {
    const result = getDoneFiles(mixed);
    expect(result.map(f => f.id)).toEqual(['d2', 'd3', 'd1']); // 3000, 2000, 1000
  });

  it('getDoneFiles treats missing completedAt as 0 (sorts last)', () => {
    const legacy = makeFile({ id: 'leg', status: 'done', progress: 100, phase: 3 }); // no completedAt
    const result = getDoneFiles([legacy, done1]);
    expect(result.map(f => f.id)).toEqual(['d1', 'leg']); // 1000 > 0
  });
});

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

  it('bridge/update_progress updates activeProgress without mutating files identity', () => {
    const file = makeFile({ id: 'x', status: 'processing' });
    const s0 = processingReducer(initialProcessingState, { type: 'queue/add', files: [file] });
    const s1 = processingReducer(s0, { type: 'bridge/update_progress', value: 0.55 });
    expect(s1.activeProgress).toBe(55);
    expect(s1.files).toBe(s0.files); // same array reference
  });

  it('bridge/file_done sets completedAt to a current timestamp', () => {
    const before = Date.now();
    const file = makeFile({ id: 'x' });
    const state = processingReducer(
      { ...initialProcessingState, files: [file] },
      { type: 'bridge/file_done', data: { id: 'x', index: 0, output_html: 'out.html', output_dir: 'dir' } },
    );
    const after = Date.now();
    const { completedAt } = state.files[0];
    expect(typeof completedAt).toBe('number');
    expect(completedAt!).toBeGreaterThanOrEqual(before);
    expect(completedAt!).toBeLessThanOrEqual(after);
  });

  it('queue/clear_completed removes only done files, leaving queued and error intact', () => {
    const files = [
      makeFile({ id: 'q1', status: 'queued' }),
      makeFile({ id: 'd1', status: 'done', progress: 100, phase: 3 }),
      makeFile({ id: 'e1', status: 'error', progress: 0, phase: 0 }),
      makeFile({ id: 'd2', status: 'done', progress: 100, phase: 3 }),
    ];
    const state = processingReducer(
      { ...initialProcessingState, files },
      { type: 'queue/clear_completed' },
    );
    expect(state.files.map(f => f.id)).toEqual(['q1', 'e1']);
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
