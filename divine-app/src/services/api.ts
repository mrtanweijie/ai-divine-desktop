import type {
  ApprovalMode,
  ChatMessage,
  Message,
  Project,
  Session,
  Settings,
  TodoItem,
  ToolEvent,
  ToolRun,
  WorkspaceCategory,
} from "@/types";
import { isTauri, openUrl } from "@/services/tauri";
import { API_BASE, apiBase, request } from "@/services/request";
import i18next from "@/i18n";

export { apiBase };

export function listSessions(
  projectId?: string
): Promise<{ sessions: Session[] }> {
  const query = projectId
    ? `?project_id=${encodeURIComponent(projectId)}`
    : "";
  return request(`/sessions${query}`);
}

export function createSession(
  title?: string,
  projectId?: string,
  approvalMode?: ApprovalMode,
  locale?: string
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

export function updateSessionApprovalMode(
  id: string,
  mode: ApprovalMode
): Promise<Session> {
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

export function cancelSessionGeneration(id: string): Promise<{ ok: boolean }> {
  return request(`/sessions/${id}/cancel`, { method: "POST" });
}

export function getSession(
  id: string,
  options?: { limit?: number; beforeId?: string }
): Promise<{
  session: Session;
  messages: Message[];
  tool_runs?: ToolRun[];
  todos?: TodoItem[];
  has_more?: boolean;
}> {
  const query = options
    ? `?limit=${options.limit ?? 100}${
        options.beforeId
          ? `&before_id=${encodeURIComponent(options.beforeId)}`
          : ""
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
  body: { name?: string; icon?: string }
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

export function exportSession(
  id: string,
  format: "markdown" | "text" | "pdf",
  locale?: string
) {
  const path = `/sessions/${id}/export?format=${format}&locale=${
    locale ?? i18next.language ?? "zh-CN"
  }`;
  const base = API_BASE.startsWith("http")
    ? API_BASE
    : `${window.location.origin}${API_BASE}`;
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

export function updateSettings(
  body: Partial<Settings> & { api_key?: string }
): Promise<Settings> {
  return request("/settings", {
    method: "PUT",
    body: JSON.stringify(body),
  });
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

function trimToolResult(result: any): any {
  if (!result || typeof result !== "object") return result;
  const copy: any = { ...result };
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
    const dataCopy: any = { ...data };
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
  return copy;
}

export function messagesToChatMessages(
  messages: Message[],
  toolRuns: ToolRun[] = [],
  todos?: TodoItem[]
): ChatMessage[] {
  const chatMessages: ChatMessage[] = [];
  let currentUserIndex = -1;
  const planTodos = todos && todos.length > 0 ? todos : undefined;
  const lastAssistantIndex = messages.reduce(
    (last, message, index) => (message.role === "assistant" ? index : last),
    -1
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
      const next = messages[index + 1];
      const start = new Date(user.created_at).getTime();
      const end = next ? new Date(next.created_at).getTime() : Date.now();
      tools.push(
        ...toolRuns
          .filter((run) => {
            const started = new Date(run.started_at).getTime();
            return started >= start && started <= end;
          })
          .map((run) => {
            let result;
            try {
              result = run.output
                ? trimToolResult(JSON.parse(run.output))
                : undefined;
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
            } satisfies ToolEvent;
          })
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
        tools.some(
          (tool) =>
            tool.tool === "write_todos" || tool.tool === "create_plan"
        )
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
            };
            return {
              name: parsed.name ?? part.content,
              size: parsed.size,
              path: parsed.path,
              content: parsed.content,
            };
          } catch {
            return { name: part.content };
          }
        }),
      tools,
    });
  });
  return chatMessages;
}
