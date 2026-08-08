import type {
  ChatMessage,
  Message,
  Session,
  Settings,
  ToolEvent,
  ToolRun,
  WorkspaceCategory,
} from "@/types";

const API_BASE = "/api";

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
): Promise<{ session: Session; messages: Message[]; tool_runs?: ToolRun[] }> {
  return request(`/sessions/${id}`);
}

export function exportSession(id: string, format: "markdown" | "text") {
  window.open(`${API_BASE}/sessions/${id}/export?format=${format}`, "_blank");
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
  toolRuns: ToolRun[] = []
): ChatMessage[] {
  const chatMessages: ChatMessage[] = [];
  let currentUserIndex = -1;
  messages.forEach((message, index) => {
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
            return {
              tool: run.tool_name,
              status: run.status === "done" ? "done" : "error",
              message: result?.message ?? run.status,
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
      tools,
    });
  });
  return chatMessages;
}
