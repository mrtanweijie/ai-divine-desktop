// Per-session deep-thinking effort memory: each conversation remembers its own
// 深度思考 level (off | low | high | max) across reloads and session switches.
// Falls back to nothing (caller applies the global default) when unset.

const EFFORT_KEY_PREFIX = "divine:session-effort:";

export function getSessionEffort(sessionId: string | null): string | null {
  if (!sessionId) return null;
  try {
    return localStorage.getItem(EFFORT_KEY_PREFIX + sessionId);
  } catch {
    return null;
  }
}

export function setSessionEffort(
  sessionId: string | null,
  effort: string
): void {
  if (!sessionId) return;
  try {
    localStorage.setItem(EFFORT_KEY_PREFIX + sessionId, effort);
  } catch {
    // ignore quota / privacy-mode errors
  }
}
