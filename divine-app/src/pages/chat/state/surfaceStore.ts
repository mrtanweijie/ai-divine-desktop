/**
 * 面板集合的纯 reducer（不持有状态，状态挂在 `ChatMessage.surfaces` 上）。
 *
 * 设计文档：`docs/design/028-a2ui-integration-20261009.md` §5.1 / §5.2 / §16.3。
 *
 * **本文件存在的唯一理由是「引用稳定」**：`MessageItem` 是 `memo` 的，
 * 流式期间每个 chunk 都会让 `setSessionMessages` 跑一次 `prev.map`。
 * 如果这里每次返回新数组（哪怕内容没变），长会话就会**全量白重渲染**
 * （044 §16.3 的最重雷区）。因此三条铁律：
 *
 * 1. `seq` 不大于已存值 → **原样返回旧引用**（乱序/重复帧直接丢弃）；
 * 2. 目标面板不存在 → 返回旧引用（不改动）；
 * 3. 只有真正改动了内容才 slice + 替换那**一个**元素。
 */

import type { UISurface } from "@/pages/chat/components/UISurface/types";

/**
 * 写入一帧面板：同 `surfaceId` 的按 `seq` 比较，**增量替换**。
 *
 * `seq` 语义（044 §5.1）：同一 surfaceId 内单调递增，用于乱序丢弃。
 * `next.seq <= current.seq` 一律丢弃 —— 重复帧与过期帧都不该让 UI 抖动。
 */
export function upsertSurface(prev: UISurface[] | undefined, next: UISurface): UISurface[] {
  const list = prev ?? [];
  const index = list.findIndex((item) => item.surfaceId === next.surfaceId);
  if (index < 0) return [...list, next];
  const current = list[index];
  if (next.seq <= current.seq) return list;
  const copy = list.slice();
  copy[index] = next;
  return copy;
}

/** 收起面板（`deleteSurface`）：保留在历史里，标记为不可交互，而非删除。 */
export function markSurfaceClosed(prev: UISurface[] | undefined, surfaceId: string): UISurface[] {
  const list = prev ?? [];
  const index = list.findIndex((item) => item.surfaceId === surfaceId);
  if (index < 0) return list;
  if (list[index].status === "closed") return list;
  const copy = list.slice();
  copy[index] = { ...list[index], status: "closed" };
  return copy;
}

/** 置/清乐观提交态（值为触发中的组件 id）。 */
export function setSurfacePending(
  prev: UISurface[] | undefined,
  surfaceId: string,
  pendingActionId: string | null,
): UISurface[] {
  const list = prev ?? [];
  const index = list.findIndex((item) => item.surfaceId === surfaceId);
  if (index < 0) return list;
  if ((list[index].pendingActionId ?? null) === pendingActionId) return list;
  const copy = list.slice();
  copy[index] = { ...list[index], pendingActionId };
  return copy;
}

/** 查找面板。 */
export function findSurface(
  prev: UISurface[] | undefined,
  surfaceId: string,
): UISurface | undefined {
  return prev?.find((item) => item.surfaceId === surfaceId);
}
