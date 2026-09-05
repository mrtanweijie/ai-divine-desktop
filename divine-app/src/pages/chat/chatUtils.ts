// Pure helpers shared between ChatPage and the chat streaming hook.
import type { ChatMessage, SubAgentItem, ToolEvent } from "@/types";
import { toWorkspaceRelative } from "@/services/workspace";

/** 用户插话标记：与后端落库/注入格式一致，MessageItem 据此渲染"补充"徽标 */
export const SUPPLEMENT_PREFIX = "[用户补充]";

/** 判断消息是否为执行中插话（[用户补充] 前缀），返回去除前缀的正文 */
export function parseSupplement(content: string): string | null {
  if (content.startsWith(`${SUPPLEMENT_PREFIX} `)) {
    return content.slice(SUPPLEMENT_PREFIX.length + 1);
  }
  return null;
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
