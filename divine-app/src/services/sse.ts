export interface SSEHandlers {
  think?: (data: { content: string }) => void;
  message?: (data: { content: string }) => void;
  tool?: (data: Record<string, unknown>) => void;
  done?: (data: { message: string }) => void;
  error?: (data: { code: string; message: string }) => void;
}

export async function consumeSSE(
  response: Response,
  handlers: SSEHandlers
): Promise<void> {
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
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
  handlers[event as keyof SSEHandlers]?.(data as never);
}
