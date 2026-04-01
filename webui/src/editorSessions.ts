export const EDITOR_SESSION_STORAGE_KEY = 'el-sbobinator.editor-sessions.v1';
const EDITOR_SESSION_TTL_DAYS = 30;

export type EditorSession = {
  audioTime?: number;
  playbackRate?: number;
  volume?: number;
  scrollTop?: number;
  savedAt?: number;
};

type EditorSessionMap = Record<string, EditorSession>;

const hasSessionState = (session: EditorSession): boolean =>
  session.audioTime !== undefined
  || session.playbackRate !== undefined
  || session.volume !== undefined
  || session.scrollTop !== undefined;

export const normalizeEditorSessions = (
  sessions: EditorSessionMap,
  now: number = Date.now(),
): EditorSessionMap => {
  const cutoff = now - EDITOR_SESSION_TTL_DAYS * 24 * 60 * 60 * 1000;

  return Object.fromEntries(
    Object.entries(sessions).flatMap(([key, session]) => {
      if (!session || typeof session !== 'object' || !hasSessionState(session)) {
        return [];
      }
      if (typeof session.savedAt === 'number') {
        return session.savedAt >= cutoff ? [[key, session]] : [];
      }
      // Preserve pre-TTL sessions created before `savedAt` existed, and
      // stamp them now so they can expire normally in the future.
      return [[key, { ...session, savedAt: now }]];
    }),
  );
};

export const loadEditorSession = (key: string): EditorSession => {
  try {
    const raw = window.localStorage.getItem(EDITOR_SESSION_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as EditorSessionMap;
    const sessions = normalizeEditorSessions(parsed);
    const normalizedRaw = JSON.stringify(sessions);
    if (normalizedRaw !== raw) {
      window.localStorage.setItem(EDITOR_SESSION_STORAGE_KEY, normalizedRaw);
    }
    return sessions[key] ?? {};
  } catch (_) {
    return {};
  }
};

export const saveEditorSession = (key: string, session: EditorSession) => {
  try {
    const now = Date.now();
    const raw = window.localStorage.getItem(EDITOR_SESSION_STORAGE_KEY) ?? '{}';
    const parsed = JSON.parse(raw) as EditorSessionMap;
    const sessions = normalizeEditorSessions(
      { ...parsed, [key]: { ...session, savedAt: now } },
      now,
    );
    window.localStorage.setItem(EDITOR_SESSION_STORAGE_KEY, JSON.stringify(sessions));
  } catch (_) {}
};
