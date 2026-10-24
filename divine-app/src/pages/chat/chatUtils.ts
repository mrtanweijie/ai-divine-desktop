// Pure helpers shared between ChatPage and the chat streaming hook.
import type { BrowserStepItem, ChatMessage, SubAgentItem, ToolEvent } from "@/types";
import { toWorkspaceRelative } from "@/services/workspace";
import { normalizeSkillName } from "@/services/skillNames";

/** 用户插话标记：与后端落库/注入格式一致，MessageItem 据此渲染"补充"徽标 */
export const SUPPLEMENT_PREFIX = "[用户补充]";

/** 判断消息是否为执行中插话（[用户补充] 前缀），返回去除前缀的正文 */
export function parseSupplement(content: string): string | null {
  if (content.startsWith(`${SUPPLEMENT_PREFIX} `)) {
    return content.slice(SUPPLEMENT_PREFIX.length + 1);
  }
  return null;
}

/** 气泡高亮用的引用片段（渲染专用，不参与发送）。 */
export type MentionSegment =
  { type: "text"; text: string } | { type: "file"; path: string } | { type: "skill"; name: string };

/**
 * `@路径`（含 `@"含 空格/路径"`）与 `/技能名`（含保留字消歧 `/skill:名称`）。
 *
 * **`/` 是技能 token 的必要前缀**，两种技能名变体都必须带它：中文名同样只能来自
 * 「用户真的敲了斜杠」的场景（`/笔记整理`）。曾因中文分支漏写 `\/`，导致任何夹在
 * 空白之后的 ≥2 字中文词（`... 模型`）乃至整条以中文开头的消息都被渲染成技能胶囊。
 *
 * 技能名的长度下限用来挡误判：ASCII 名要求 ≥ 3 个字符（`A/B` 不算技能），
 * 中文名要求 ≥ 2 个字符（后端技能名可以是「笔记整理」这类中文）。
 */
const MENTION_TOKEN_RE =
  /@"([^"\n]+)"|@([^\s@"]+)|\/skill:([A-Za-z\u4e00-\u9fff][A-Za-z0-9_.\-\u4e00-\u9fff]*)|(\/(?:[A-Za-z][A-Za-z0-9_.-]{2,}|[\u4e00-\u9fff][A-Za-z0-9_.\-\u4e00-\u9fff]{1,}))/g;

/**
 * 把用户消息正文切成「普通文本 / @文件 / /技能」片段。
 *
 * 触发条件与输入框候选一致（`@`、`/` 前必须是行首或空白），所以 `a@b.com`、`和/或`
 * 不会被误判。词法命中只是**候选**：传入 `knownSkills` 时以真实技能名集合为准，
 * 未命中的 token 还原成普通文本（`见 /docs 目录` 的 `/docs` 是路径不是技能）。
 *
 * 不传 `knownSkills` 时退回纯词法判断——这是集合尚未就绪（或取不到）时的降级路径，
 * 宁可多标也不要把真技能降级成普通文本。
 *
 * 注意这仍是**渲染层启发式**：后端只信结构化 mentions 数组，不依赖这里的解析结果。
 */
export function parseMentionSegments(
  text: string,
  knownSkills?: ReadonlySet<string>,
): MentionSegment[] {
  if (!text) return [];
  const segments: MentionSegment[] = [];
  let cursor = 0;
  MENTION_TOKEN_RE.lastIndex = 0;
  let match = MENTION_TOKEN_RE.exec(text);
  while (match !== null) {
    const start = match.index;
    const prev = start === 0 ? "" : text[start - 1];
    // 前缀不是行首或空白 → 当作普通文本跳过（不消耗 cursor）
    if (prev !== "" && !/\s/.test(prev)) {
      match = MENTION_TOKEN_RE.exec(text);
      continue;
    }
    const [raw, quoted, plain, skillAlias, skillName] = match;
    if (start > cursor) segments.push({ type: "text", text: text.slice(cursor, start) });
    const filePath = quoted || plain;
    if (filePath) {
      segments.push({ type: "file", path: filePath });
    } else {
      const name = normalizeSkillName(skillAlias || skillName || "");
      // 校验失败 → 原样当文本（游标照常前进，拼接结果与原文逐字一致）
      if (knownSkills && !knownSkills.has(name)) {
        segments.push({ type: "text", text: raw });
      } else {
        segments.push({ type: "skill", name });
      }
    }
    cursor = start + raw.length;
    match = MENTION_TOKEN_RE.exec(text);
  }
  if (cursor < text.length) segments.push({ type: "text", text: text.slice(cursor) });
  return segments;
}

export function acceptedFilesKey(path: string): string {
  return `divine:accepted-files:${path}`;
}

export function changedFilePathsFromResult(result: unknown): string[] {
  // Flatten file paths out of tool result payloads (files/results arrays).
  const paths: string[] = [];
  if (!result || typeof result !== "object") return paths;
  const payload = result as Record<string, unknown>;
  if (typeof payload.filepath === "string") paths.push(payload.filepath);

  const data = payload.data;
  if (data && typeof data === "object") {
    const dataRecord = data as Record<string, unknown>;
    for (const listKey of ["files", "results"]) {
      const items = dataRecord[listKey];
      if (!Array.isArray(items)) continue;
      for (const item of items) {
        if (!item || typeof item !== "object") continue;
        const record = item as Record<string, unknown>;
        const path =
          typeof record.filepath === "string"
            ? record.filepath
            : typeof record.path === "string"
              ? record.path
              : null;
        if (path) paths.push(path);
      }
    }
  }
  return [...new Set(paths)];
}

export function changedFileRel(base: string, raw: string): string | null {
  const normalized = raw.replace(/\\/g, "/").replace(/^\.\//, "");
  if (/^([A-Za-z]:)?\//.test(normalized)) {
    return toWorkspaceRelative(base, normalized);
  }
  return normalized;
}

export function expandedWorkspaceWidth(leftWidth: number): number {
  return Math.max(480, window.innerWidth - leftWidth);
}

export function upsertTool(tools: ToolEvent[], next: ToolEvent): ToolEvent[] {
  const index = tools.findIndex((tool) =>
    next.call_id ? tool.call_id === next.call_id : tool.tool === next.tool,
  );
  if (index === -1) {
    return [...tools, { ...next, status: next.status || "preparing" }];
  }
  const updated = [...tools];
  updated[index] = { ...updated[index], ...next };
  return updated;
}

export function upsertSubAgent(items: SubAgentItem[], next: SubAgentItem): SubAgentItem[] {
  const index = items.findIndex((item) => item.id === next.id);
  if (index === -1) {
    return [...items, next];
  }
  const updated = [...items];
  updated[index] = { ...updated[index], ...next };
  return updated;
}

/** browser 步骤心跳：按 step 号去重（同 step 更新），保持时间线有序 */
export function upsertBrowserStep(
  items: BrowserStepItem[],
  next: BrowserStepItem,
): BrowserStepItem[] {
  const index = items.findIndex((item) => item.step === next.step);
  if (index === -1) {
    return [...items, next];
  }
  const updated = [...items];
  updated[index] = { ...updated[index], ...next };
  return updated;
}

/** 仍在「进行中」的状态：这些状态在 ToolStatusCard 上显示 loading 图标 */
export const UNSETTLED_TOOL_STATUSES: ReadonlySet<ToolEvent["status"]> = new Set([
  "preparing",
  "running",
  "confirm",
]);

/**
 * 把仍在进行中的工具卡结算为 error。
 *
 * 用于「用户主动停止」：SSE 连接已被 abort，在跑的工具收不到后续 done 事件，
 * 不结算就会永久停在 loading（一直持续到刷新）。状态对齐「刷新后」的结果——
 * 服务端把非 done 的 run 一律映射为 error（见 services/api.ts）。
 * 无进行中条目时原样返回，避免无谓的重渲染。
 */
export function settleInFlightTools(tools: ToolEvent[]): ToolEvent[] {
  if (!tools.some((tool) => UNSETTLED_TOOL_STATUSES.has(tool.status))) return tools;
  return tools.map((tool) =>
    UNSETTLED_TOOL_STATUSES.has(tool.status) ? { ...tool, status: "error" } : tool,
  );
}

/**
 * 把「本地仍显示进行中」的工具卡按服务端的权威状态收敛。
 *
 * 为什么需要：本地 tools 是 SSE 事件逐条攒出来的，而服务端恢复出的状态**只会是
 * done / error**（见 services/api.ts 的 messagesToChatMessages）。此前 mergeLocalTools
 * 无条件优先本地，于是**任何一条 done 事件丢失**（断流重连、竞态、标签页休眠）都会让
 * 卡片永久停在 loading，一直持续到下次刷新——刷新后反而正常，因为那时走的是服务端状态。
 *
 * 匹配键用**工具名**而不是 call_id：两侧的 call_id 不是同一个标识
 * （服务端是 tool_run 行 id，本地是 LLM 的 tool_call_id）。
 * 同名多次调用时**按出现顺序一一对齐**——已结算的本地条目也要占掉一个服务端名额，
 * 否则后面未结算的那个会错位拿到别人的状态。
 */
function settleToolStatuses(
  localTools: ToolEvent[] | undefined,
  serverTools: ToolEvent[],
): ToolEvent[] {
  if (!localTools?.length) return serverTools;
  const serverByName = new Map<string, ToolEvent[]>();
  for (const tool of serverTools) {
    const list = serverByName.get(tool.tool);
    if (list) list.push(tool);
    else serverByName.set(tool.tool, [tool]);
  }
  if (serverByName.size === 0) return localTools;
  // 每个工具名各自的消费游标：本地每条（无论是否已结算）都占一个服务端名额
  const cursor = new Map<string, number>();
  return localTools.map((tool) => {
    const group = serverByName.get(tool.tool);
    if (!group?.length) return tool;
    const index = cursor.get(tool.tool) ?? 0;
    cursor.set(tool.tool, index + 1);
    const counterpart = group[index];
    if (!counterpart) return tool;
    // 只在「本地未结算 + 服务端已结算」时收敛
    if (!UNSETTLED_TOOL_STATUSES.has(tool.status)) return tool;
    if (UNSETTLED_TOOL_STATUSES.has(counterpart.status)) return tool;
    return { ...tool, status: counterpart.status };
  });
}

export function mergeLocalTools(local: ChatMessage[], restored: ChatMessage[]) {
  // Keep live tool/file state after a completed stream replaces local messages.
  if (local.length !== restored.length) return restored;
  return restored.map((message, index) => ({
    ...message,
    tools: settleToolStatuses(local[index]?.tools, message.tools),
    files: local[index]?.files?.length ? local[index].files : message.files,
  }));
}
