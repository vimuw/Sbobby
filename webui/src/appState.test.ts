import { describe, expect, it } from 'vitest';

import { getDoneFiles, getPendingFiles, initialProcessingState, isSuccessfulProcessDone, processingReducer, type FileItem } from './appState';


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

  it('isSuccessfulProcessDone only returns true for all-success completions', () => {
    expect(isSuccessfulProcessDone({ completed: 1, failed: 0, total: 1 })).toBe(true);
    expect(isSuccessfulProcessDone({ completed: 0, failed: 1, total: 1 })).toBe(false);
    expect(isSuccessfulProcessDone({ completed: 1, failed: 1, total: 2 })).toBe(false);
    expect(isSuccessfulProcessDone({ cancelled: true, completed: 1, failed: 0, total: 1 })).toBe(false);
    expect(isSuccessfulProcessDone(undefined)).toBe(false);
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

  it('queue/reorder returns same state when fromIndex equals toIndex', () => {
    const files = [makeFile({ id: 'a' }), makeFile({ id: 'b' })];
    const state = { ...initialProcessingState, files };
    const next = processingReducer(state, { type: 'queue/reorder', fromIndex: 0, toIndex: 0 });
    expect(next).toBe(state);
  });

  it('queue/reorder returns same state when fromIndex is out of bounds', () => {
    const files = [makeFile({ id: 'a' })];
    const state = { ...initialProcessingState, files };
    const next = processingReducer(state, { type: 'queue/reorder', fromIndex: 5, toIndex: 0 });
    expect(next).toBe(state);
  });

  it('queue/update_source does not alter non-matching files', () => {
    const files = [makeFile({ id: 'x' }), makeFile({ id: 'y' })];
    const state = processingReducer(
      { ...initialProcessingState, files },
      { type: 'queue/update_source', id: 'x', path: '/new.mp3', name: 'new.mp3' },
    );
    expect(state.files[1].id).toBe('y');
  });

  it('queue/remove removes the targeted file', () => {
    const files = [makeFile({ id: 'del' }), makeFile({ id: 'keep' })];
    const state = processingReducer(
      { ...initialProcessingState, files },
      { type: 'queue/remove', id: 'del' },
    );
    expect(state.files.map(f => f.id)).toEqual(['keep']);
  });

  it('queue/update_source updates path/name/size/duration for matching file', () => {
    const file = makeFile({ id: 'src1', path: '/old.mp3', name: 'old.mp3', size: 100, duration: 10 });
    const state = processingReducer(
      { ...initialProcessingState, files: [file] },
      { type: 'queue/update_source', id: 'src1', path: '/new.mp3', name: 'new.mp3', size: 200, duration: 20 },
    );
    expect(state.files[0].path).toBe('/new.mp3');
    expect(state.files[0].name).toBe('new.mp3');
    expect(state.files[0].size).toBe(200);
  });

  it('queue/retry_one resets only the targeted error file', () => {
    const files = [
      makeFile({ id: 'a', status: 'error', errorText: 'fail', progress: 0, phase: 0 }),
      makeFile({ id: 'b', status: 'error', errorText: 'fail2', progress: 0, phase: 0 }),
    ];
    const state = processingReducer(
      { ...initialProcessingState, files },
      { type: 'queue/retry_one', id: 'a' },
    );
    expect(state.files[0].status).toBe('queued');
    expect(state.files[0].errorText).toBeUndefined();
    expect(state.files[1].status).toBe('error');
  });

  it('queue/clear_all empties file list', () => {
    const state = processingReducer(
      { ...initialProcessingState, files: [makeFile()] },
      { type: 'queue/clear_all' },
    );
    expect(state.files).toEqual([]);
  });

  it('app/set_status changes appState', () => {
    const state = processingReducer(initialProcessingState, { type: 'app/set_status', status: 'canceling' });
    expect(state.appState).toBe('canceling');
  });

  it('default case returns same state for unknown action', () => {
    // @ts-expect-error testing unknown action type
    const state = processingReducer(initialProcessingState, { type: 'unknown/action' });
    expect(state).toBe(initialProcessingState);
  });

  it('queue/update_source falls back to existing duration when not provided', () => {
    const file = makeFile({ id: 'u', duration: 60 });
    const state = processingReducer(
      { ...initialProcessingState, files: [file] },
      { type: 'queue/update_source', id: 'u', path: '/new.mp3', name: 'new.mp3' },
    );
    expect(state.files[0].duration).toBe(60);
  });

  it('bridge/update_progress returns same state when progress value is unchanged', () => {
    const base = { ...initialProcessingState, activeProgress: 55 };
    const next = processingReducer(base, { type: 'bridge/update_progress', value: 0.55 });
    expect(next).toBe(base);
  });

  it('bridge/set_work_totals falls back to existing values when data fields are null', () => {
    const base = { ...initialProcessingState, workTotals: { chunks: 5, macro: 4, boundary: 3 } };
    const state = processingReducer(
      base,
      { type: 'bridge/set_work_totals', data: { chunks: null, macro: null, boundary: null } },
    );
    expect(state.workTotals).toEqual({ chunks: 5, macro: 4, boundary: 3 });
  });

  it('bridge/set_work_totals updates workTotals', () => {
    const state = processingReducer(
      initialProcessingState,
      { type: 'bridge/set_work_totals', data: { chunks: 10, macro: 8, boundary: 7 } },
    );
    expect(state.workTotals).toEqual({ chunks: 10, macro: 8, boundary: 7 });
  });

  it('bridge/update_work_done updates workDone for a kind', () => {
    const state = processingReducer(
      initialProcessingState,
      { type: 'bridge/update_work_done', data: { kind: 'chunks', done: 5 } },
    );
    expect(state.workDone.chunks).toBe(5);
  });

  it('bridge/update_work_done returns same state when value is unchanged', () => {
    const base = { ...initialProcessingState, workDone: { chunks: 5, macro: 0, boundary: 0 } };
    const next = processingReducer(base, { type: 'bridge/update_work_done', data: { kind: 'chunks', done: 5 } });
    expect(next).toBe(base);
  });

  it('bridge/process_done with cancelled=true does not touch queued files', () => {
    const files = [
      makeFile({ id: 'p1', status: 'processing' }),
      makeFile({ id: 'q1', status: 'queued' }),
    ];
    const state = processingReducer(
      { ...initialProcessingState, files },
      { type: 'bridge/process_done', data: { cancelled: true, total: 1 } },
    );
    expect(state.files[1].status).toBe('queued');
  });

  it('bridge/set_current_file does not alter non-matching files', () => {
    const files = [makeFile({ id: 'active' }), makeFile({ id: 'other' })];
    const state = processingReducer(
      { ...initialProcessingState, files },
      { type: 'bridge/set_current_file', data: { id: 'active', index: 0, total: 2 } },
    );
    expect(state.files[1].status).toBe('queued');
  });

  it('bridge/file_failed uses fallback message when error is undefined', () => {
    const file = makeFile({ id: 'f', status: 'processing' });
    const state = processingReducer(
      { ...initialProcessingState, files: [file] },
      { type: 'bridge/file_failed', data: { id: 'f', index: 0, error: undefined } },
    );
    expect(state.files[0].errorText).toBe('Elaborazione non completata.');
  });

  it('bridge/register_step_time initialises stepMetrics for first call', () => {
    const state = processingReducer(
      initialProcessingState,
      { type: 'bridge/register_step_time', data: { kind: 'chunks', seconds: 5 } },
    );
    expect(state.stepMetrics.chunks?.avgSeconds).toBe(5);
    expect(state.stepMetrics.chunks?.done).toBe(1);
  });

  it('bridge/register_step_time uses EMA on subsequent calls', () => {
    const withPrev = {
      ...initialProcessingState,
      stepMetrics: { chunks: { avgSeconds: 10, done: 1, total: 5 }, macro: null, boundary: null },
    };
    const state = processingReducer(
      withPrev,
      { type: 'bridge/register_step_time', data: { kind: 'chunks', seconds: 4 } },
    );
    expect(state.stepMetrics.chunks?.avgSeconds).toBeCloseTo(0.4 * 4 + 0.6 * 10);
  });

  it('bridge/file_done does not alter non-matching files', () => {
    const files = [makeFile({ id: 'target' }), makeFile({ id: 'other' })];
    const state = processingReducer(
      { ...initialProcessingState, files },
      { type: 'bridge/file_done', data: { id: 'target', index: 0, output_html: 'out.html', output_dir: 'dir' } },
    );
    expect(state.files[1].status).toBe('queued');
  });

  it('bridge/file_failed does not alter non-matching files', () => {
    const files = [makeFile({ id: 'fail1', status: 'processing' }), makeFile({ id: 'ok', status: 'queued' })];
    const state = processingReducer(
      { ...initialProcessingState, files },
      { type: 'bridge/file_failed', data: { id: 'fail1', index: 0, error: 'timeout' } },
    );
    expect(state.files[1].status).toBe('queued');
  });

  it('bridge/update_phase returns same state when phase unchanged (early return)', () => {
    const state = { ...initialProcessingState, currentPhase: 'Fase 1/3' };
    const next = processingReducer(state, { type: 'bridge/update_phase', text: 'Fase 1/3' });
    expect(next).toBe(state);
  });

  it('bridge/update_phase updates currentPhase when changed', () => {
    const state = { ...initialProcessingState, currentPhase: 'Fase 1/3' };
    const next = processingReducer(state, { type: 'bridge/update_phase', text: 'Fase 2/3' });
    expect(next.currentPhase).toBe('Fase 2/3');
  });

  it('bridge/update_model returns same state when model unchanged', () => {
    const state = { ...initialProcessingState, currentModel: 'gemini-2.5-flash' };
    const next = processingReducer(state, { type: 'bridge/update_model', model: 'gemini-2.5-flash' });
    expect(next).toBe(state);
  });

  it('bridge/update_model updates currentModel when changed', () => {
    const state = { ...initialProcessingState, currentModel: 'gemini-2.5-flash' };
    const next = processingReducer(state, { type: 'bridge/update_model', model: 'gemini-2.5-pro' });
    expect(next.currentModel).toBe('gemini-2.5-pro');
  });

  it('bridge/file_failed marks file as error with errorText', () => {
    const file = makeFile({ id: 'err1', status: 'processing' });
    const state = processingReducer(
      { ...initialProcessingState, files: [file] },
      { type: 'bridge/file_failed', data: { id: 'err1', index: 0, error: 'quota_daily_limit_phase1' } },
    );
    expect(state.files[0].status).toBe('error');
    expect(state.files[0].errorText).toBe('quota_daily_limit_phase1');
    expect(state.files[0].progress).toBe(0);
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
