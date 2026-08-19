// Per-session model memory: each conversation remembers which configured
// model (by id) it uses across reloads and session switches.
// Falls back to nothing (caller applies the global default = the active
// model in Settings) when unset.

const MODEL_KEY_PREFIX = "divine:session-model:";

export function getSessionModelId(sessionId: string | null): string | null {
  if (!sessionId) return null;
  try {
    return localStorage.getItem(MODEL_KEY_PREFIX + sessionId);
  } catch {
    return null;
  }
}

export function setSessionModelId(
  sessionId: string | null,
  modelId: string
): void {
  if (!sessionId) return;
  try {
    localStorage.setItem(MODEL_KEY_PREFIX + sessionId, modelId);
  } catch {
    // ignore quota / privacy-mode errors
  }
}
