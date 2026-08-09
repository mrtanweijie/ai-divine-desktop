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
  approvalMode?: ApprovalMode
): Promise<Session> {
  return request("/sessions", {
    method: "POST",
    body: JSON.stringify({
      title,
      project_id: projectId,
      approval_mode: approvalMode,
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

export function getSession(
  id: string
): Promise<{
  session: Session;
  messages: Message[];
  tool_runs?: ToolRun[];
  todos?: TodoItem[];
}> {
  return request(`/sessions/${id}`);
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
  format: "markdown" | "text" | "pdf"
) {
  const path = `/sessions/${id}/export?format=${format}`;
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
              result = run.output ? JSON.parse(run.output) : undefined;
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
              status: run.status === "done" ? "done" : "error",
              message: result?.message ?? run.status,
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
        planTodos && message.role === "assistant" && index === lastAssistantIndex
          ? planTodos
          : undefined,
      files: message.parts
        .filter((part) => part.type === "file")
        .map((part) => {
          try {
            const parsed = JSON.parse(part.content) as { name?: string };
            return { name: parsed.name ?? part.content };
          } catch {
            return { name: part.content };
          }
        }),
      tools,
    });
  });
  return chatMessages;
}
