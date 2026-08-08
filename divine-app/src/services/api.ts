import type {
  ChatMessage,
  Message,
  Session,
  Settings,
  TodoItem,
  ToolEvent,
  ToolRun,
  WorkspaceCategory,
} from "@/types";
import { isTauri, openUrl } from "@/services/tauri";

const API_BASE =
  import.meta.env.VITE_SERVICE_API_URL?.replace(/\/+$/, "") || "/api";

export function apiBase(): string {
  return API_BASE;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function listSessions(): Promise<{ sessions: Session[] }> {
  return request("/sessions");
}

export function createSession(title?: string): Promise<Session> {
  return request("/sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
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
