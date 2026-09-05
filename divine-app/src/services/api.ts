import type {
  ApprovalMode,
  ChatMessage,
  ChatPreprocess,
  CompactResult,
  ContextUsage,
  McpServerStatus,
  Message,
  Project,
  Session,
  Settings,
  SettingsSaveBody,
  SubAgentItem,
  TodoItem,
  ToolEvent,
  ToolRun,
  WorkspaceCategory,
} from "@/types";
import { isTauri, openUrl } from "@/services/tauri";
import { API_BASE, apiBase, request } from "@/services/request";
import i18next from "@/i18n";

export { apiBase };

export function listSessions(projectId?: string): Promise<{ sessions: Session[] }> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return request(`/sessions${query}`);
}

export interface SearchResult extends Session {
  snippet?: string;
}

export function searchSessions(
  q: string,
  projectId?: string,
): Promise<{ sessions: SearchResult[] }> {
  const params = new URLSearchParams({ q });
  if (projectId) params.set("project_id", projectId);
  return request(`/sessions/search?${params}`);
}

export function createSession(
  title?: string,
  projectId?: string,
  approvalMode?: ApprovalMode,
  locale?: string,
): Promise<Session> {
  return request("/sessions", {
    method: "POST",
    body: JSON.stringify({
      title,
      project_id: projectId,
      approval_mode: approvalMode,
      locale: locale ?? i18next.language ?? "zh-CN",
    }),
  });
}

export function updateSessionApprovalMode(id: string, mode: ApprovalMode): Promise<Session> {
  return request(`/sessions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ approval_mode: mode }),
  });
}

export function renameSession(id: string, title: string): Promise<Session> {
  return request(`/sessions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export function deleteSession(id: string): Promise<void> {
  return request(`/sessions/${id}`, { method: "DELETE" });
}

export function clearSession(id: string): Promise<unknown> {
  return request(`/sessions/${id}/clear`, { method: "POST" });
}

/** 保存选项卡片的已选状态（选择后置灰，刷新/重开会话后保持） */
export function saveMessageChoiceState(
  messageId: string,
  state: Record<string, unknown>,
): Promise<{ message: ChatMessage }> {
  return request(`/sessions/messages/${messageId}/choice_state`, {
    method: "POST",
    body: JSON.stringify({ state }),
  });
}

export function cancelSessionGeneration(id: string): Promise<{ ok: boolean }> {
  return request(`/sessions/${id}/cancel`, { method: "POST" });
}

/**
 * 用户插话（steering）：agent 执行中主动补充信息。
 * 409（无活跃流）等失败会 reject，由调用方降级为常规发送。
 */
export function injectSupplement(id: string, content: string): Promise<{ ok: boolean }> {
  return request(`/sessions/${id}/inject`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

/** Token usage breakdown for the composer context ring. */
export function getContextUsage(id: string): Promise<ContextUsage> {
  return request(`/sessions/${id}/context-usage`);
}

/** Manually compact a session's early conversation into a summary. */
export function compactSession(id: string): Promise<CompactResult> {
  return request(`/sessions/${id}/compact`, { method: "POST" });
}

export function getSession(
  id: string,
  options?: { limit?: number; beforeId?: string },
): Promise<{
  session: Session;
  messages: Message[];
  tool_runs?: ToolRun[];
  todos?: TodoItem[];
  has_more?: boolean;
}> {
  const query = options
    ? `?limit=${options.limit ?? 100}${
        options.beforeId ? `&before_id=${encodeURIComponent(options.beforeId)}` : ""
      }`
    : "";
  return request(`/sessions/${id}${query}`);
}

export function listProjects(): Promise<{ projects: Project[] }> {
  return request("/projects");
}

export function createProject(body: {
  name: string;
  path?: string;
  icon?: string;
}): Promise<Project> {
  return request("/projects", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateProject(
  id: string,
  body: { name?: string; icon?: string },
): Promise<Project> {
  return request(`/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function renameProject(id: string, name: string): Promise<Project> {
  return request(`/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function deleteProject(id: string): Promise<void> {
  return request(`/projects/${id}`, { method: "DELETE" });
}

export function updateProjectOrder(id: string, sortOrder: number): Promise<Project> {
  return request(`/projects/${id}/order`, {
    method: "PATCH",
    body: JSON.stringify({ sort_order: sortOrder }),
  });
}

export function pinProject(id: string, pinned: boolean): Promise<Project> {
  return request(`/projects/${id}/pin`, {
    method: "PATCH",
    body: JSON.stringify({ pinned }),
  });
}

export function reorderProjects(orders: { id: string; sort_order: number }[]): Promise<void> {
  return request("/projects/reorder", {
    method: "POST",
    body: JSON.stringify({ orders }),
  });
}

export function exportSession(id: string, format: "markdown" | "text" | "pdf", locale?: string) {
  const path = `/sessions/${id}/export?format=${format}&locale=${
    locale ?? i18next.language ?? "zh-CN"
  }`;
  const base = API_BASE.startsWith("http") ? API_BASE : `${window.location.origin}${API_BASE}`;
  const url = `${base}${path}`;
  if (isTauri()) {
    void openUrl(url);
  } else {
    window.open(url, "_blank");
  }
}

export function getSettings(): Promise<Settings> {
  return request("/settings");
}

export function updateSettings(body: SettingsSaveBody): Promise<Settings> {
  return request("/settings", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/** MCP 服务器实时状态（含连接尝试与工具清单，后端有短缓存） */
export function getMcpServers(): Promise<{ servers: McpServerStatus[] }> {
  return request("/mcp/servers");
}

/** 单个 MCP 服务器连接测试 */
export function testMcpServer(serverId: string): Promise<McpServerStatus> {
  return request(`/mcp/servers/${encodeURIComponent(serverId)}/test`, {
    method: "POST",
  });
}

export interface BalanceInfo {
  available: boolean;
  balance?: string;
  currency?: string;
  reason?: string;
  error?: string;
}

export function getBalance(modelId?: string): Promise<BalanceInfo> {
  const query = modelId ? `?model_id=${encodeURIComponent(modelId)}` : "";
  return request(`/settings/balance${query}`);
}

export function getWorkspace(): Promise<{
  workspace: string;
  categories: WorkspaceCategory[];
}> {
  return request("/files");
}

export function downloadUrl(url: string): string {
  return `${API_BASE}${url.startsWith("/api") ? url.slice(4) : url}`;
}

export interface PdfPreviewResult {
  pages: string[];
  page_count: number;
  truncated: boolean;
}

/** Render a local PDF to page images via the backend (avoids the webview's
 * native PDF viewer, whose zoom controls are not styleable). */
export async function fetchPdfPreview(path: string): Promise<PdfPreviewResult> {
  return request<PdfPreviewResult>("/files/pdf-preview", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export interface DocumentPreviewResult {
  content: string;
  truncated: boolean;
}

export async function fetchDocumentPreview(path: string): Promise<DocumentPreviewResult> {
  return request<DocumentPreviewResult>("/files/document-preview", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

function trimToolResult<T>(result: T): T {
  if (!result || typeof result !== "object") return result;
  const copy: Record<string, unknown> = {
    ...(result as Record<string, unknown>),
  };
  for (const key of ["content", "stdout", "stderr"]) {
    const value = copy[key];
    if (typeof value === "string" && value.length > 4000) {
      copy[key] = i18next.t("common.truncated", "{{prefix}}\n...[截断，共 {{count}} 字符]", {
        prefix: value.slice(0, 4000),
        count: value.length,
      });
    }
  }
  const data = copy.data;
  if (data && typeof data === "object") {
    const dataCopy: Record<string, unknown> = {
      ...(data as Record<string, unknown>),
    };
    for (const key of ["content", "stdout", "stderr", "text"]) {
      const value = dataCopy[key];
      if (typeof value === "string" && value.length > 4000) {
        dataCopy[key] = i18next.t("common.truncated", "{{prefix}}\n...[截断，共 {{count}} 字符]", {
          prefix: value.slice(0, 4000),
          count: value.length,
        });
      }
    }
    if (Array.isArray(dataCopy.results) && dataCopy.results.length > 12) {
      dataCopy.results = [
        ...dataCopy.results.slice(0, 12),
        { truncated: true, count: dataCopy.results.length - 12 },
      ];
    }
    copy.data = dataCopy;
  }
  return copy as T;
}

/** 解析本地预整理标记部件（type="preprocess"）。 */
function parsePreprocessPart(parts: Message["parts"]): ChatPreprocess | undefined {
  const part = parts.find((p) => p.type === "preprocess");
  if (!part) return undefined;
  try {
    return JSON.parse(part.content) as ChatPreprocess;
  } catch {
    return undefined;
  }
}

export function messagesToChatMessages(
  messages: Message[],
  toolRuns: ToolRun[] = [],
  todos?: TodoItem[],
): ChatMessage[] {
  const chatMessages: ChatMessage[] = [];
  let currentUserIndex = -1;
  const planTodos = todos && todos.length > 0 ? todos : undefined;
  const lastAssistantIndex = messages.reduce(
    (last, message, index) => (message.role === "assistant" ? index : last),
    -1,
  );
  messages.forEach((message, index) => {
    if (
      message.role === "tool" ||
      (message.role === "assistant" &&
        !message.content &&
        message.parts.some((part) => part.type === "tool_calls"))
    ) {
      return;
    }
    if (message.role === "user") {
      currentUserIndex = index;
    }
    const tools: ToolEvent[] = [];
    if (message.role === "assistant" && currentUserIndex !== -1) {
      const user = messages[currentUserIndex];
      // 归属窗口右边界用本条消息自身的创建时间：答案消息在整轮跑完后才落库，
      // 本轮的 web_search/fetch 等工具运行必然早于它。不能再用"下一条消息"
      // 做右边界——重答会在回答后追加相邻 assistant 消息（中间没有用户消息），
      // 导致同一次工具运行同时落进两条消息的窗口，工具卡片重复展示。
      const start = new Date(user.created_at).getTime();
      const end = new Date(message.created_at).getTime();
      tools.push(
        ...toolRuns
          .filter((run) => {
            const started = new Date(run.started_at).getTime();
            return started >= start && started <= end;
          })
          .map((run) => {
            let result;
            try {
              result = run.output ? trimToolResult(JSON.parse(run.output)) : undefined;
            } catch {
              result = undefined;
            }
            let command: string | undefined;
            try {
              const input = run.input ? JSON.parse(run.input) : undefined;
              command = input?.command;
            } catch {
              command = undefined;
            }
            return {
              tool: run.tool_name,
              call_id: run.id,
              status: run.status === "done" ? "done" : "error",
              message: result?.message ?? run.status,
              messageKey: result?.messageKey,
              messageParams: result?.messageParams,
              command,
              result,
              turn: run.turn ?? undefined,
              run_id: run.id,
              started_at: run.started_at,
              duration_ms: run.duration_ms ?? undefined,
            } satisfies ToolEvent;
          }),
      );
    }
    chatMessages.push({
      id: message.id,
      role: message.role,
      content: message.content,
      created_at: message.created_at,
      think: message.parts.find((part) => part.type === "think")?.content,
      todos:
        planTodos &&
        message.role === "assistant" &&
        index === lastAssistantIndex &&
        tools.some((tool) => tool.tool === "write_todos" || tool.tool === "create_plan")
          ? planTodos
          : undefined,
      files: message.parts
        .filter((part) => part.type === "file")
        .map((part) => {
          try {
            const parsed = JSON.parse(part.content) as {
              name?: string;
              size?: number;
              path?: string;
              content?: string;
              preprocess_original?: boolean;
            };
            return {
              name: parsed.name ?? part.content,
              size: parsed.size,
              path: parsed.path,
              content: parsed.content,
              preprocess_original: parsed.preprocess_original,
            };
          } catch {
            return { name: part.content };
          }
        })
        // 预整理原文附件（preprocess_original）只服务模型，UI 由
        // preprocess 部件展示可展开原文，避免重复卡片
        .filter((file) => !(file as { preprocess_original?: boolean }).preprocess_original),
      preprocess: parsePreprocessPart(message.parts),
      tools,
      subagents: subagentsFromToolRuns(tools),
      choice_state: message.choice_state,
      source: message.source,
      token_usage: message.token_usage,
    });
  });
  return chatMessages;
}

/** Rebuild the sub-agent panel from a persisted run_subagents tool run. */
export function subagentsFromToolRuns(tools: ToolEvent[]): SubAgentItem[] {
  const run = tools.find((tool) => tool.tool === "run_subagents");
  const result = run?.result as
    | {
        data?: { subagents?: SubAgentItem[] };
        subagents?: SubAgentItem[];
        results?: SubAgentItem[];
      }
    | undefined;
  const items = result?.data?.subagents ?? result?.subagents ?? result?.results ?? [];
  if (!Array.isArray(items) || items.length === 0) return [];
  return items
    .filter(
      (item): item is SubAgentItem =>
        !!item && typeof item.id === "string" && typeof item.name === "string",
    )
    .map((item) => ({
      id: item.id,
      name: item.name,
      // Persisted runs are terminal; never show "running" after reload.
      status: item.status === "error" ? "error" : "done",
      summary: item.summary,
      error: item.error,
      changed_files: item.changed_files,
      changed_count: item.changed_count,
    }));
}

/* ------------------------------------------------------------------ */
/*  Git project info                                                   */
/* ------------------------------------------------------------------ */

export interface GitFileInfo {
  path: string;
  status: "modified" | "added" | "deleted" | "renamed" | "untracked";
}

export interface GitCommitInfo {
  message: string;
  relative_time: string;
}

export interface GitInfo {
  is_git: boolean;
  branch: string;
  ahead: number;
  behind: number;
  dirty: boolean;
  total_changes: number;
  files: GitFileInfo[];
  last_commit: GitCommitInfo | null;
  remote_url: string;
  stash_count: number;
}

export function getGitInfo(projectPath: string): Promise<GitInfo> {
  return request<GitInfo>(`/git/info?path=${encodeURIComponent(projectPath)}`);
}
