import { describe, expect, it, vi } from 'vitest';

import { createBridge } from './bridge';
import { initialProcessingState, processingReducer, type ProcessingAction } from './appState';


describe('createBridge', () => {
  it('dispatches progress and file lifecycle events', () => {
    let state = initialProcessingState;
    const dispatch = (action: ProcessingAction) => {
      state = processingReducer(state, action);
    };

    const appendConsole = vi.fn();
    const onRegenerate = vi.fn();
    const onAskNewKey = vi.fn();
    const onBatchDone = vi.fn();
    const onFileDone = vi.fn();

    const bridge = createBridge({
      dispatch,
      appendConsole,
      onRegenerate,
      onAskNewKey,
      onBatchDone,
      onFileDone,
    });

    dispatch({
      type: 'queue/add',
      files: [{
        id: 'abc',
        name: 'lesson.mp3',
        size: 1,
        duration: 1,
        status: 'queued',
        progress: 0,
        phase: 0,
      }],
    });

    bridge.setCurrentFile({ id: 'abc', index: 0, total: 1 });
    bridge.setWorkTotals({ chunks: 4, macro: 2, boundary: 1 });
    bridge.updateWorkDone({ kind: 'chunks', done: 1, total: 4 });
    bridge.registerStepTime({ kind: 'chunks', seconds: 3.5, done: 1, total: 4 });
    bridge.updateProgress(0.42);
    bridge.fileDone({ id: 'abc', index: 0, output_html: 'out.html', output_dir: 'dist' });
    bridge.processDone({ completed: 1, failed: 0, total: 1 });

    expect(state.files[0].status).toBe('done');
    expect(state.files[0].progress).toBe(100);
    expect(state.workTotals.chunks).toBe(4);
    expect(state.workDone.chunks).toBe(1);
    expect(onFileDone).toHaveBeenCalledTimes(1);
    expect(onBatchDone).toHaveBeenCalledTimes(1);
  });

  it('routes prompts to their handlers', () => {
    const onRegenerate = vi.fn();
    const onAskNewKey = vi.fn();
    const bridge = createBridge({
      dispatch: vi.fn(),
      appendConsole: vi.fn(),
      onRegenerate,
      onAskNewKey,
      onBatchDone: vi.fn(),
      onFileDone: vi.fn(),
    });

    bridge.askRegenerate({ filename: 'lesson.mp3' });
    bridge.askNewKey();

    expect(onRegenerate).toHaveBeenCalledWith({ filename: 'lesson.mp3' });
    expect(onAskNewKey).toHaveBeenCalledTimes(1);
  });
});
