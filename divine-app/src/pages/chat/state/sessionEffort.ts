// Per-session deep-thinking effort memory: each conversation remembers its own
// 深度思考 level (off | low | high | max) across reloads and session switches.
// Falls back to nothing (caller applies the global default) when unset.

import { storageGetRaw, storageSetRaw } from "@/services/storage";

const EFFORT_KEY_PREFIX = "divine:session-effort:";

export function getSessionEffort(sessionId: string | null): string | null {
  if (!sessionId) return null;
  return storageGetRaw(EFFORT_KEY_PREFIX + sessionId);
}

export function setSessionEffort(sessionId: string | null, effort: string): void {
  if (!sessionId) return;
  storageSetRaw(EFFORT_KEY_PREFIX + sessionId, effort);
}

/** 全局默认开关 → 输入框档位：think_default 开时取 reasoning_effort（缺省 high）。 */
export function defaultComposerEffort(
  settings: {
    think_default: boolean;
    reasoning_effort?: string;
  } | null,
): string {
  return settings?.think_default ? (settings.reasoning_effort ?? "high") : "off";
}
