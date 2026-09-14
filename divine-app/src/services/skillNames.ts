// 会话可见技能名集合：气泡渲染判断 `/xxx` 是否为真技能的判据。
//
// 词法正则只能给"候选"——`见 /docs 目录` 里的 `/docs` 得靠真实技能集合排除；
// 集合来自 `GET /api/workspace/skill-names`（与 `/` 候选同源、无 8 条截断）。
import { listSkillNames } from "@/services/api";

/** 缓存存活时间：兜住"后端已变更但前端没收到失效通知"的兜底窗口。 */
const TTL_MS = 60_000;

interface SkillNamesEntry {
  names: ReadonlySet<string>;
  at: number;
}

const cache = new Map<string, SkillNamesEntry>();
const inflight = new Map<string, Promise<ReadonlySet<string> | null>>();

function cacheKey(sessionId?: string | null): string {
  return sessionId || "__default__";
}

/**
 * 技能 token → 规范化技能名：去掉前导 `/` 与 `skill:` 消歧前缀，统一小写。
 *
 * 输出既是胶囊展示文本（不带语法前缀——图标 + 等宽字形已表意），也是与技能名集合
 * 比对用的键：`/photo-editorial`、`/skill:photo-editorial`、`Photo-Editorial` 归一。
 */
export function normalizeSkillName(raw: string): string {
  return raw
    .trim()
    .replace(/^\/+/, "")
    .replace(/^skill:/i, "")
    .trim()
    .toLowerCase();
}

/** 同步读取仍新鲜的缓存（供 hook 首帧直接用，避免先空一帧）。 */
export function peekSessionSkillNames(sessionId?: string | null): ReadonlySet<string> | undefined {
  const entry = cache.get(cacheKey(sessionId));
  if (entry && Date.now() - entry.at < TTL_MS) return entry.names;
  return undefined;
}

/** 技能集合可能已变（安装/卸载/手动刷新）时调用，丢弃全部会话缓存。 */
export function invalidateSessionSkillNames(): void {
  cache.clear();
}

/**
 * 取会话技能名集合：同会话并发调用只发一次请求；失败不写缓存（下次重试）。
 * 返回 `null` 表示取不到——调用方应退回纯词法判断。
 */
export function getSessionSkillNames(
  sessionId?: string | null,
): Promise<ReadonlySet<string> | null> {
  const key = cacheKey(sessionId);
  const pending = inflight.get(key);
  if (pending) return pending;
  const task = listSkillNames(sessionId)
    .then((payload) => {
      const names: ReadonlySet<string> = new Set(
        (payload.names ?? []).map(normalizeSkillName).filter(Boolean),
      );
      cache.set(key, { names, at: Date.now() });
      return names;
    })
    .catch(() => null)
    .finally(() => {
      inflight.delete(key);
    });
  inflight.set(key, task);
  return task;
}
