export interface SSEHandlers {
  think?: (data: { content: string }) => void;
  message?: (data: { content: string }) => void;
  plan?: (data: { items: Record<string, unknown>[] }) => void;
  todo_update?: (data: {
    id: string;
    status: string;
    result?: string;
  }) => void;
  tool?: (data: Record<string, unknown>) => void;
  scheduled_tasks_changed?: (data: {
    tasks: Record<string, unknown>[];
  }) => void;
  calendar_events_changed?: (data: {
    events: Record<string, unknown>[];
  }) => void;
  done?: (data: { message: string }) => void;
  error?: (data: {
    code: string;
    message: string;
    messageKey?: string;
    messageParams?: Record<string, unknown>;
  }) => void;
}

const SSE_DEBUG =
  import.meta.env.DEV || import.meta.env.VITE_API_DEBUG === "true";

function logSSE(event: string, data: unknown) {
  if (!SSE_DEBUG) return;
  let text = JSON.stringify(data) ?? "undefined";
  if (text.length > 4000) {
    text = `${text.slice(0, 4000)}... (truncated)`;
  }
  console.log(`[sse] event ${event}`, text);
}

export async function consumeSSE(
  response: Response,
  handlers: SSEHandlers
): Promise<void> {
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  if (SSE_DEBUG) {
    console.log("[sse] connected");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      handleEvent(part, handlers);
    }
  }
  if (buffer.trim()) {
    handleEvent(buffer, handlers);
  }
  if (SSE_DEBUG) {
    console.log("[sse] done");
  }
}

function handleEvent(part: string, handlers: SSEHandlers) {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of part.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (!dataLines.length) return;
  const raw = dataLines.join("\n");
  if (raw === "[DONE]") return;
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(raw);
  } catch {
    return;
  }
  logSSE(event, data);
  handlers[event as keyof SSEHandlers]?.(data as never);
}
