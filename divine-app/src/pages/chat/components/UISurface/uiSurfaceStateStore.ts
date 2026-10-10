/**
 * 面板编辑态（"用户改了但还没提交"的值）的存储。
 *
 * 设计文档：`docs/design/028-a2ui-integration-20261009.md` §5.5。
 *
 * 这是**四个时间点里的第 ① ② 个**，与"面板最终态"（`ui_surface` part）和
 * "动作提交"（新 user 消息）**必须分开存**：
 *
 * | 时间点 | 落点 | 生命周期 |
 * | --- | --- | --- |
 * | ① 编辑中（未提交） | 本文件的模块级 Map | 组件卸载/滚出视口后仍在；刷新丢 |
 * | ② 同上，抗刷新 | DB `ui_surface_states`（本文件防抖写入） | 刷新/切会话都保持 |
 * | ③ 点按钮提交 | 新 user 消息（后端做） | 永久 |
 * | ④ 面板最终态 | assistant 的 `ui_surface` part（后端做） | 永久 |
 *
 * 三条硬约束（044 §5.5）：
 * 1. 未提交的编辑态**禁止写 `messages`** —— 它不是对话内容，还会挤占
 *    LLM 上下文预算（token 预算 70% 治理）；
 * 2. 模块级 Map 是**零延迟、跨 mount** 的那一层，DB 只是抗刷新的兜底；
 * 3. 写入策略照 `ChoiceBlock` 的 `choiceStateStore`：**失败不阻塞交互**
 *    （`saveMessageUiSurfaceState` 的 rejection 只吞掉，不弹错）。
 *
 * key 用 `sessionId|surfaceId`，**不是** `messageId|surfaceId`：
 * 面板所属的消息 id 在流式期间是前端乐观 id（`local-assistant-*`），
 * `done` 之后会整段换成服务端 id（`useChatStream` 的 done 处理器会
 * `getSession` 重建消息列表）。若拿 messageId 当 key，同一块面板在
 * id 漂移前后是两个 key —— 流式期间改的值会在回合结束时凭空消失。
 * 会话内 `surfaceId` 唯一，所以 `sessionId|surfaceId` 既稳定又不跨会话污染。
 */

import { setByPath } from "./dataModel";
import { listSessionUiSurfaceStates, saveUiSurfaceState } from "@/services/api";

interface EditEntry {
  /** path → 用户写入的值（只存改过的字段，不是整份 dataModel）。 */
  values: Record<string, unknown>;
  /** 最近一次写库时带上的 message_id（只作回放定位的元信息）。 */
  messageId: string;
  timer: ReturnType<typeof setTimeout> | null;
}

/** 模块级缓存：跨组件卸载存活，但**刷新即丢**（历史从 DB 恢复）。 */
const editStore = new Map<string, EditEntry>();

/** 防抖窗口：连续打字只在停下来后落一次库。 */
const DEBOUNCE_MS = 400;

function keyOf(sessionId: string | null | undefined, surfaceId: string): string {
  return `${sessionId ?? ""}|${surfaceId}`;
}

/** 读当前编辑态（返回副本，调用方改它不会污染 store）。 */
export function readSurfaceEdits(
  sessionId: string | null | undefined,
  surfaceId: string,
): Record<string, unknown> | undefined {
  const entry = editStore.get(keyOf(sessionId, surfaceId));
  return entry ? { ...entry.values } : undefined;
}

/** 记一次编辑：立即写内存，防抖落 DB。 */
export function writeSurfaceEdit(
  sessionId: string | null | undefined,
  surfaceId: string,
  path: string,
  value: unknown,
  messageId?: string,
): void {
  if (!sessionId) return;
  const key = keyOf(sessionId, surfaceId);
  const entry = editStore.get(key) ?? { values: {}, messageId: "", timer: null };
  entry.values[path] = value;
  // 取最新一次看到的消息 id：回合结束后它会从乐观 id 变成服务端 id。
  if (messageId) entry.messageId = messageId;
  editStore.set(key, entry);
  if (entry.timer) clearTimeout(entry.timer);
  entry.timer = setTimeout(() => {
    entry.timer = null;
    void saveUiSurfaceState(sessionId, {
      surface_id: surfaceId,
      ...(entry.messageId ? { message_id: entry.messageId } : {}),
      data: entry.values,
    }).catch(() => {
      // 保存失败不阻塞交互：内存里那份仍然有效，下次编辑会再试。
    });
  }, DEBOUNCE_MS);
}

/**
 * 清掉编辑态（动作提交成功后调用，§8.3）。
 * 面板已被新一轮覆盖，旧编辑态不再有意义。
 */
export function clearSurfaceEdits(sessionId: string | null | undefined, surfaceId: string): void {
  const key = keyOf(sessionId, surfaceId);
  const entry = editStore.get(key);
  if (entry?.timer) clearTimeout(entry.timer);
  editStore.delete(key);
}

/** 从 DB 载入的编辑态灌进内存（**内存中更新的值优先**，不被旧数据覆盖）。 */
export function hydrateSurfaceEdits(
  sessionId: string | null | undefined,
  surfaceId: string,
  values: Record<string, unknown> | undefined | null,
  messageId?: string,
): void {
  if (!sessionId || !values || !Object.keys(values).length) return;
  const key = keyOf(sessionId, surfaceId);
  const entry = editStore.get(key) ?? { values: {}, messageId: "", timer: null };
  entry.values = { ...values, ...entry.values };
  if (messageId) entry.messageId = messageId;
  editStore.set(key, entry);
}

/**
 * 从服务端拉某会话的全部编辑态灌进内存（加载历史时调用，§5.5 ② 的读取端）。
 *
 * **必须在"消息落进 React state 之前"完成**：面板只在挂载时读一次编辑态
 * （`useState` 初始值），晚一步恢复就等于没恢复 —— 所以 `useSessionLoader`
 * 是在 `await` 到 states 之后才 `setSessionMessages` 的。
 *
 * 拉取失败静默：编辑态是增强项，不该让会话加载失败。
 * 一条也没有也是常态（大多数会话里用户从没改过面板）。
 */
export async function hydrateSessionSurfaceEdits(sessionId: string): Promise<void> {
  if (!sessionId) return;
  try {
    const { states } = await listSessionUiSurfaceStates(sessionId);
    for (const state of states ?? []) {
      if (!state?.surface_id) continue;
      hydrateSurfaceEdits(sessionId, state.surface_id, state.data, state.message_id);
    }
  } catch {
    // 恢复编辑态是增强项，失败不影响会话加载。
  }
}

/**
 * 把编辑态叠加到面板 dataModel 上（挂载时用，抗刷新）。
 *
 * `surfaceId` 的编辑态是**跨回合**的：面板被新一轮原地覆盖（§8.3）时
 * 用户刚填的值应当还在；但 `status === "closed"` 的历史快照不走这里 ——
 * 那是"面板当时长什么样"的归档，未提交的编辑态不该污染它（§5.5 硬约束 1）。
 */
export function applyEditsToDataModel(
  sessionId: string | null | undefined,
  surfaceId: string,
  dataModel: Record<string, unknown>,
): Record<string, unknown> {
  const edits = readSurfaceEdits(sessionId, surfaceId);
  if (!edits) return dataModel;
  let next = dataModel;
  for (const [path, value] of Object.entries(edits)) {
    next = setByPath(next, path, value);
  }
  return next;
}
