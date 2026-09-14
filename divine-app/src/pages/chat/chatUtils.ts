// Pure helpers shared between ChatPage and the chat streaming hook.
import type { ChatMessage, SubAgentItem, ToolEvent } from "@/types";
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

export function mergeLocalTools(local: ChatMessage[], restored: ChatMessage[]) {
  // Keep live tool/file state after a completed stream replaces local messages.
  if (local.length !== restored.length) return restored;
  return restored.map((message, index) => ({
    ...message,
    tools: local[index]?.tools?.length ? local[index].tools : message.tools,
    files: local[index]?.files?.length ? local[index].files : message.files,
  }));
}
