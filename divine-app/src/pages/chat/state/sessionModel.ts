// Per-session model memory: each conversation remembers which configured
// model (by id) it uses across reloads and session switches.
// Falls back to nothing (caller applies the global default = the active
// model in Settings) when unset.

import { storageGetRaw, storageSetRaw } from "@/services/storage";

const MODEL_KEY_PREFIX = "divine:session-model:";

export function getSessionModelId(sessionId: string | null): string | null {
  if (!sessionId) return null;
  return storageGetRaw(MODEL_KEY_PREFIX + sessionId);
}

export function setSessionModelId(
  sessionId: string | null,
  modelId: string
): void {
  if (!sessionId) return;
  storageSetRaw(MODEL_KEY_PREFIX + sessionId, modelId);
}
