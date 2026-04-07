import { describe, expect, it } from 'vitest';

import type { FileItem } from './appState';
import { deserializeQueueFile, serializeQueueFile } from './hooks/useQueuePersistence';

function roundTrip(file: FileItem): FileItem {
  return deserializeQueueFile(JSON.parse(JSON.stringify(serializeQueueFile(file))), 0);
}

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

describe('useQueuePersistence — serialization contract', () => {
  it('completedAt is preserved through a JSON round-trip', () => {
    const ts = 1712491234567;
    const restored = roundTrip(makeFile({ status: 'done', progress: 100, phase: 3, completedAt: ts }));
    expect(restored.completedAt).toBe(ts);
  });

  it('completedAt missing on legacy entries is restored as undefined', () => {
    const restored = roundTrip(makeFile({ status: 'done', progress: 100, phase: 3 }));
    expect(restored.completedAt).toBeUndefined();
  });

  it('done file retains status, outputHtml and outputDir after round-trip', () => {
    const file = makeFile({
      id: 'abc',
      status: 'done',
      progress: 100,
      phase: 3,
      outputHtml: '/out/lesson.html',
      outputDir: '/out',
      completedAt: 1712491234567,
    });
    const restored = roundTrip(file);
    expect(restored.status).toBe('done');
    expect(restored.outputHtml).toBe('/out/lesson.html');
    expect(restored.outputDir).toBe('/out');
    expect(restored.completedAt).toBe(1712491234567);
  });

  it('processing status is downgraded to queued on restore', () => {
    const file = makeFile({ status: 'processing', progress: 50, phase: 1 });
    const restored = roundTrip(file);
    expect(restored.status).toBe('queued');
    expect(restored.progress).toBe(0);
  });

  it('error status and errorText are preserved on restore', () => {
    const file = makeFile({ status: 'error', progress: 0, phase: 0, errorText: 'timeout' });
    const restored = roundTrip(file);
    expect(restored.status).toBe('error');
    expect(restored.errorText).toBe('timeout');
  });
});
