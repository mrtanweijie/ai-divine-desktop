// Per-session deep-thinking effort memory: each conversation remembers its own
// 深度思考 level (off | low | high | max) across reloads and session switches.
// Falls back to nothing (caller applies the global default) when unset.

import { storageGetRaw, storageSetRaw } from "@/services/storage";

const EFFORT_KEY_PREFIX = "divine:session-effort:";

export function getSessionEffort(sessionId: string | null): string | null {
  if (!sessionId) return null;
  return storageGetRaw(EFFORT_KEY_PREFIX + sessionId);
}

export function setSessionEffort(
  sessionId: string | null,
  effort: string
): void {
  if (!sessionId) return;
  storageSetRaw(EFFORT_KEY_PREFIX + sessionId, effort);
}
