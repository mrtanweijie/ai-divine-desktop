export const API_BASE =
  import.meta.env.VITE_SERVICE_API_URL?.replace(/\/+$/, "") || "/api";

const API_DEBUG =
  import.meta.env.DEV || import.meta.env.VITE_API_DEBUG === "true";

const SENSITIVE_KEY_RE =
  /(api[_-]?key|glm[_-]?api[_-]?key|password|token|secret|authorization)/i;

interface ApiRequestInit extends RequestInit {
  throwOnError?: boolean;
}

export function apiBase(): string {
  return API_BASE;
}

function parseBody(body: BodyInit | null | undefined): unknown {
  if (typeof body !== "string" || !body) return body;
  try {
    return JSON.parse(body);
  } catch {
    return body;
  }
}

function redact(
  value: unknown,
  seen = new WeakSet<object>(),
  depth = 0
): unknown {
  if (value === null || typeof value !== "object") {
    if (typeof value === "string" && value.length > 2000) {
      return `${value.slice(0, 2000)}...(${value.length} chars)`;
    }
    return value;
  }
  if (depth > 5) return "[max-depth]";
  if (seen.has(value)) return "[circular]";
  seen.add(value);
  if (Array.isArray(value)) {
    return value.slice(0, 50).map((item) => redact(item, seen, depth + 1));
  }
  const result: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(
    value as Record<string, unknown>
  )) {
    result[key] = SENSITIVE_KEY_RE.test(key)
      ? "***"
      : redact(item, seen, depth + 1);
  }
  return result;
}

function serializeLog(value: unknown): string {
  let text: string;
  try {
    text = JSON.stringify(value) ?? "undefined";
  } catch {
    text = String(value);
  }
  if (text.length > 8000) {
    text = `${text.slice(0, 8000)}... (truncated)`;
  }
  return text;
}

function logRequest(method: string, url: string, init: RequestInit) {
  if (!API_DEBUG) return;
  console.log(
    `[api] request ${method} ${url}`,
    serializeLog({
      body: redact(parseBody(init.body)),
      headers: redact(init.headers),
      signal: init.signal ? "abortable" : undefined,
    })
  );
}

function logResponse(
  method: string,
  url: string,
  value: unknown,
  durationMs: number
) {
  if (!API_DEBUG) return;
  console.log(
    `[api] response ${method} ${url}`,
    serializeLog({
      output: redact(value),
      durationMs: Math.round(durationMs),
    })
  );
}

function logError(method: string, url: string, error: unknown) {
  if (!API_DEBUG) return;
  // 主动 abort（如 StartupGate 轮询后端就绪、用户中断流式请求）属于预期行为，
  // 不算错误，不打 warning 避免刷屏误导。
  if (error instanceof Error && error.name === "AbortError") return;
  console.warn(
    `[api] error ${method} ${url}`,
    error instanceof Error ? error.message : error
  );
}

export async function request<T>(
  path: string,
  init: ApiRequestInit = {}
): Promise<T> {
  const method = init.method ?? "GET";
  const url = `${API_BASE}${path}`;
  const startedAt = performance.now();
  logRequest(method, url, init);

  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const { throwOnError, ...fetchInit } = init;

  let response: Response;
  try {
    response = await fetch(url, { ...fetchInit, headers });
  } catch (error) {
    logError(method, url, error);
    throw error;
  }

  if (!response.ok) {
    const detail = await response.text();
    const durationMs = performance.now() - startedAt;
    logResponse(
      method,
      url,
      { ok: false, status: response.status, detail },
      durationMs
    );
    if (throwOnError === false) return undefined as T;
    throw new Error(detail || `HTTP ${response.status}`);
  }

  if (response.status === 204) {
    logResponse(method, url, undefined, performance.now() - startedAt);
    return undefined as T;
  }

  const raw = await response.text();
  let data: unknown = raw;
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      data = raw;
    }
  }
  logResponse(method, url, data, performance.now() - startedAt);
  return data as T;
}

export async function requestRaw(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const method = init.method ?? "GET";
  const url = `${API_BASE}${path}`;
  const startedAt = performance.now();
  logRequest(method, url, init);

  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  try {
    const response = await fetch(url, { ...init, headers });
    logResponse(
      method,
      url,
      { ok: response.ok, status: response.status },
      performance.now() - startedAt
    );
    return response;
  } catch (error) {
    logError(method, url, error);
    throw error;
  }
}
