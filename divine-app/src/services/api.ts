import type {
  ApprovalMode,
  ChatMessage,
  ChatPreprocess,
  CompactResult,
  ContextUsage,
  McpServerStatus,
  MentionCandidate,
  MentionKind,
  Message,
  MessagePart,
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
import { parseUISurfaceIR } from "@/pages/chat/components/UISurface/parseUISurface";
import type { UISurface } from "@/pages/chat/components/UISurface/types";
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

/** 面板动作请求体（design 028 §8.1）。 */
export interface SurfaceActionBody {
  session_id: string;
  /** 面板所属的 assistant 消息 id（定位与回显用）。流式期间可能是前端乐观 id。 */
  message_id: string;
  surface_id: string;
  /** 幂等键：60s 内重复只跑一轮（前端连点两次不会起两个回合）。 */
  action_id: string;
  name: string;
  /** 触发它的按钮文案：后端拿它当**可见 user 正文**的主体（§8.2 的 ⚠️）。 */
  label: string;
  /** action.context 求值结果。 */
  context: Record<string, unknown>;
  /** 面板当前态（含用户改过的值）。 */
  data_model: Record<string, unknown>;
  // —— 以下与 /stream_chat 同构，由 useChatStream 按输入框当前档位补齐 ——
  approval_mode?: ApprovalMode;
  think?: boolean;
  reasoning_effort?: string;
  locale?: string;
  ui_theme?: string;
  model_id?: string | null;
}

/**
 * 动作请求里"面板那一半"的字段。由 `UISurfaceBlock` 收集，
 * 交给 `useChatStream.submitSurfaceAction` 补齐会话/模型档位后再发出去
 * —— 面板不该知道当前用的是哪个模型、要不要深度思考。
 */
export interface SurfaceActionInput {
  sessionId: string;
  messageId: string;
  surfaceId: string;
  /** 幂等键，由 `useSurfaceAction` 生成。 */
  actionId: string;
  name: string;
  label: string;
  context: Record<string, unknown>;
  dataModel: Record<string, unknown>;
}

/**
 * 保存面板编辑态（用户改了但还没提交的值，抗刷新，design 028 §5.5 ②）。
 *
 * **按会话写**而不是按消息：`ui_surface_states` 的主键是 `surface_id`，
 * 而消息 id 在流式期间是前端乐观 id（`local-assistant-*`）、`done` 之后
 * 又会换成服务端 id —— 拿它当写入口会让编辑态在 id 漂移时整份丢失。
 */
export function saveUiSurfaceState(
  sessionId: string,
  body: { surface_id: string; message_id?: string; data: Record<string, unknown> },
): Promise<{ ok: boolean }> {
  return request(`/sessions/${sessionId}/ui-surface-state`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** 面板编辑态的持久化形态（`GET /sessions/{id}/ui-surface-states`）。 */
export interface PersistedUISurfaceState {
  surface_id: string;
  message_id: string;
  data: Record<string, unknown>;
}

/** 取该会话下全部面板编辑态，加载历史后一次性恢复（§5.5 ② 的读取端）。 */
export function listSessionUiSurfaceStates(
  sessionId: string,
): Promise<{ states: PersistedUISurfaceState[] }> {
  return request(`/sessions/${sessionId}/ui-surface-states`);
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

export function listMentionCandidates(params: {
  q?: string;
  sessionId?: string | null;
  kinds?: MentionKind[];
  limit?: number;
  signal?: AbortSignal;
}): Promise<{ workspace: string | null; items: MentionCandidate[]; truncated: boolean }> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.sessionId) search.set("session_id", params.sessionId);
  if (params.kinds?.length) search.set("kinds", params.kinds.join(","));
  if (params.limit) search.set("limit", String(params.limit));
  const query = search.toString();
  return request(`/workspace/mentions${query ? `?${query}` : ""}`, {
    signal: params.signal,
  });
}

/**
 * 会话可见的**全部**技能名（无候选上限）。
 *
 * 消息气泡用它判断正文里的 `/xxx` 是不是真技能：候选接口按上限截断，只能保证"弹层
 * 可见的前 N 条"，拿它做全集会把超出上限的真技能误降级成普通文本。
 */
export function listSkillNames(
  sessionId?: string | null,
): Promise<{ workspace: string | null; names: string[] }> {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return request(`/workspace/skill-names${query}`);
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

export interface PptxPreviewResult {
  pages: string[];
  page_count: number;
  truncated: boolean;
}

/** Render a local .pptx to slide images via the backend (same approach as the
 * PDF preview: the webview cannot render slides natively, and the previous
 * text extraction made decks look like plain transcripts). */
export async function fetchPptxPreview(path: string): Promise<PptxPreviewResult> {
  return request<PptxPreviewResult>("/files/pptx-preview", {
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

/** tool_run.output 的解析结果。ok=false 即 JSON.parse 失败（与原 try/catch 等价）。 */
interface ParsedToolOutput {
  raw: string;
  ok: boolean;
  value: unknown;
}

/**
 * run.id → 已解析的 output。
 *
 * tool_run 落库后 output 不再变化，故按 id 缓存是安全的；仍存 raw 做校验，
 * raw 变了就重新解析。loadSession 与 loadChangedFiles 各自 getSession 一次，
 * 这份缓存把同一条 output 的 JSON.parse 从两次降到一次。
 */
const toolOutputCache = new Map<string, ParsedToolOutput>();
/** 缓存字节上限：防止超长工具结果（read_file 动辄数 MB）把内存吃满 */
const TOOL_OUTPUT_CACHE_BYTES = 32 * 1024 * 1024;
let toolOutputCacheBytes = 0;

function parseToolOutput(run: ToolRun): ParsedToolOutput | undefined {
  const raw = run.output;
  if (!raw) return undefined;
  const hit = toolOutputCache.get(run.id);
  if (hit && hit.raw === raw) return hit;

  let ok = true;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    ok = false;
    value = undefined;
  }
  const entry: ParsedToolOutput = { raw, ok, value };

  // 单条就超预算的结果不进缓存（否则一次就顶满），按次解析即可
  if (raw.length > TOOL_OUTPUT_CACHE_BYTES) return entry;

  if (hit) {
    toolOutputCache.delete(run.id);
    toolOutputCacheBytes -= hit.raw.length;
  }
  while (toolOutputCacheBytes + raw.length > TOOL_OUTPUT_CACHE_BYTES) {
    const oldest = toolOutputCache.keys().next().value;
    if (oldest === undefined) break;
    toolOutputCacheBytes -= toolOutputCache.get(oldest)?.raw.length ?? 0;
    toolOutputCache.delete(oldest);
  }
  toolOutputCache.set(run.id, entry);
  toolOutputCacheBytes += raw.length;
  return entry;
}

/** 供 useSessionLoader.loadChangedFiles 复用同一条 output 的解析结果。 */
export function parseToolRunOutput(run: ToolRun): { ok: boolean; value: unknown } | undefined {
  const parsed = parseToolOutput(run);
  return parsed ? { ok: parsed.ok, value: parsed.value } : undefined;
}

/** 单条 tool_run 的预解析结果：时间戳 / result / command / 原下标。 */
interface PreparedRun {
  run: ToolRun;
  /** started_at 的毫秒值（预解析，避免内层循环反复 new Date） */
  startedMs: number;
  /** 截断后的 result，直接挂到 ToolEvent 上 */
  result: unknown;
  command: string | undefined;
  /** toolRuns 里的原始下标，用于还原顺序 */
  index: number;
}

function toToolEvent({ run, result, command }: PreparedRun): ToolEvent {
  const shaped = result as
    | {
        message?: string;
        messageKey?: string;
        messageParams?: Record<string, unknown>;
      }
    | undefined;
  return {
    tool: run.tool_name,
    call_id: run.id,
    status: run.status === "done" ? "done" : "error",
    message: shaped?.message ?? run.status,
    messageKey: shaped?.messageKey,
    messageParams: shaped?.messageParams,
    command,
    result: result as ToolEvent["result"],
    turn: run.turn ?? undefined,
    run_id: run.id,
    started_at: run.started_at,
    duration_ms: run.duration_ms ?? undefined,
  } satisfies ToolEvent;
}

/**
 * 预解析一遍 toolRuns，并按 started_at 建升序下标表。
 *
 * 原先「时间戳 + JSON.parse + JSON.parse(input)」都写在 messages.forEach 里，
 * 同一条 run 会按它落入的窗口数被反复计算。这里每条只算一次。
 */
function prepareRuns(toolRuns: ToolRun[]): {
  prepared: PreparedRun[];
  byStart: number[];
} {
  const prepared: PreparedRun[] = toolRuns.map((run, index) => {
    const parsed = parseToolOutput(run);
    let command: string | undefined;
    if (run.input) {
      try {
        command = (JSON.parse(run.input) as { command?: string } | null)?.command;
      } catch {
        command = undefined;
      }
    }
    return {
      run,
      startedMs: new Date(run.started_at).getTime(),
      result: parsed?.ok ? trimToolResult(parsed.value) : undefined,
      command,
      index,
    };
  });
  const byStart = prepared
    .map((item) => item.index)
    .sort((a, b) => prepared[a].startedMs - prepared[b].startedMs);
  return { prepared, byStart };
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
  // 预解析（见 prepareRuns / parseToolOutput 的说明）：每条 run 只算一次，
  // 消息时间戳也只算一次，避免在窗口归属里反复 new Date() / JSON.parse()。
  const { prepared, byStart } = prepareRuns(toolRuns);
  const runAt = (offset: number) => prepared[byStart[offset]];
  const messageMs = messages.map((m) => new Date(m.created_at).getTime());
  /** byStart 里第一个 startedMs >= target 的偏移 */
  const lowerBound = (target: number) => {
    let lo = 0;
    let hi = byStart.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (runAt(mid).startedMs < target) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  };
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
      // 归属窗口右边界用本条消息自身的创建时间：答案消息在整轮跑完后才落库，
      // 本轮的 web_search/fetch 等工具运行必然早于它。不能再用"下一条消息"
      // 做右边界——重答会在回答后追加相邻 assistant 消息（中间没有用户消息），
      // 导致同一次工具运行同时落进两条消息的窗口，工具卡片重复展示。
      const start = messageMs[currentUserIndex];
      const end = messageMs[index];
      // byStart 按 startedMs 升序：二分到第一个 >= start 的位置后顺序扫到 > end，
      // 命中集合与原先的 filter(started >= start && started <= end) 完全一致。
      const hits: number[] = [];
      for (let offset = lowerBound(start); offset < byStart.length; offset += 1) {
        const item = runAt(offset);
        if (item.startedMs > end) break;
        hits.push(item.index);
      }
      // 还原 toolRuns 的原始顺序（原先 filter 保序，UI 工具卡顺序依赖它）
      hits.sort((a, b) => a - b);
      tools.push(...hits.map((runIndex) => toToolEvent(prepared[runIndex])));
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
      surfaces: surfacesFromParts(message.parts, message.id),
      source: message.source,
      token_usage: message.token_usage,
    });
  });
  return chatMessages;
}

/**
 * 从 `ui_surface` part 重建面板（design 028 §5.3 历史回放）。
 *
 * 回放出来的面板一律 `status:"closed"`：输入控件只读、按钮禁用，
 * 避免用户对一条已经结束的历史回合做"看起来能点但点了没用"的操作。
 * 解析失败的面板**直接跳过**（一处坏数据不该毁掉整段历史），
 * 与流式路径的"非法就忽略"保持一致。
 */
export function surfacesFromParts(
  parts: MessagePart[],
  messageId: string,
): UISurface[] | undefined {
  const surfaces: UISurface[] = [];
  for (const part of parts) {
    if (part.type !== "ui_surface") continue;
    let raw: unknown;
    try {
      raw = JSON.parse(part.content);
    } catch {
      continue;
    }
    const parsed = parseUISurfaceIR(raw, { status: "closed", messageId });
    if (parsed.ok) surfaces.push(parsed.surface);
  }
  return surfaces.length ? surfaces : undefined;
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
