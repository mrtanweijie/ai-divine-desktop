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

export function setSessionModelId(sessionId: string | null, modelId: string): void {
  if (!sessionId) return;
  storageSetRaw(MODEL_KEY_PREFIX + sessionId, modelId);
}

/** 解析会话应使用的模型条目 id：优先会话记忆，回落设置默认（active）；
 * 记住/默认的条目未配置 API Key 时，回落到第一个已配置 Key 的提供商。 */
export function resolveModelTargetId(
  models: Array<{ id: string; has_api_key?: boolean }>,
  rememberedId: string | null,
  activeId: string | null,
): string | null {
  const rawId = rememberedId ?? activeId;
  const baseId = rawId?.split("::")[0] ?? null;
  const entry = baseId ? models.find((m) => m.id === baseId) : undefined;
  return entry && entry.has_api_key ? rawId : (models.find((m) => m.has_api_key)?.id ?? null);
}
