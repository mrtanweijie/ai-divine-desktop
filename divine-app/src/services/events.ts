// 全局事件流客户端：连接 `${API_BASE}/events`，把后端广播的事件分发给订阅者。
//
// 与对话回合内的 SSE（services/sse.ts）不同，这条连接是**常驻**的，用于接收
// 后台发生的事件——例如调度器跑完定时任务、顺手建了专属会话。
// EventSource 自带断线重连，不需要自己写退避逻辑。

import { API_BASE } from "@/services/request";

export type AppEventName =
  "ready" | "sessions_changed" | "session_messages_changed" | "task_finished";

type AppEventListener = (data: Record<string, unknown>) => void;

const EVENT_NAMES: AppEventName[] = [
  "ready",
  "sessions_changed",
  "session_messages_changed",
  "task_finished",
];

const listeners = new Map<AppEventName, Set<AppEventListener>>();
let source: EventSource | null = null;
let started = false;

function dispatch(name: AppEventName, data: Record<string, unknown>): void {
  const set = listeners.get(name);
  if (!set) return;
  set.forEach((listener) => {
    try {
      listener(data);
    } catch {
      // 单个订阅者抛错不影响其他订阅者
    }
  });
}

function ensureSource(): void {
  if (started) return;
  started = true;
  try {
    source = new EventSource(`${API_BASE}/events`);
  } catch {
    // 构造失败（例如环境不支持）：下次订阅再试
    started = false;
    return;
  }
  EVENT_NAMES.forEach((name) => {
    source?.addEventListener(name, (event) => {
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse((event as MessageEvent).data || "{}");
      } catch {
        // 载荷不是 JSON 就当空对象处理
      }
      dispatch(name, data);
    });
  });
}

/**
 * 订阅一个全局事件；返回取消订阅函数。
 *
 * 首次订阅时才会真正建立 EventSource 连接（懒启动）。
 */
export function subscribeAppEvent(name: AppEventName, listener: AppEventListener): () => void {
  ensureSource();
  let set = listeners.get(name);
  if (!set) {
    set = new Set();
    listeners.set(name, set);
  }
  set.add(listener);
  return () => {
    set?.delete(listener);
  };
}

/** 仅供测试/调试：断开并重置连接状态。 */
export function resetAppEventSource(): void {
  source?.close();
  source = null;
  started = false;
  listeners.clear();
}
