// 生成任务（035）：一份 store 供任务面板 / 对话工具卡 / 侧栏徽标三处消费。
//
// 035 §9.3：三处各自拉数据必然打架（面板显示完成、卡片还在转圈）——
// 状态变化走全局事件流 media_tasks_changed，断线用 5s 轮询兜底。

import { API_BASE, request } from "@/services/request";
import { subscribeAppEvent } from "@/services/events";
import { notifyTaskFinished } from "@/services/scheduledTasks";
import { toast } from "@/components/ui/Toast";
import i18next from "@/i18n";

export interface MediaTask {
  id: string;
  session_id?: string | null;
  kind: string;
  provider: string;
  model?: string | null;
  prompt: string;
  params: Record<string, unknown>;
  status: "queued" | "running" | "succeeded" | "failed" | "expired" | "cancelled";
  file_path?: string | null;
  extras: Record<string, unknown>;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

type Listener = (tasks: MediaTask[]) => void;

let cache: MediaTask[] | null = null;
let inflight: Promise<MediaTask[]> | null = null;
const listeners = new Set<Listener>();
let pollTimer: ReturnType<typeof setInterval> | null = null;
let eventBound = false;

function isRunning(task: MediaTask): boolean {
  return task.status === "queued" || task.status === "running";
}

function needsPolling(): boolean {
  return (cache ?? []).some(isRunning);
}

function notify(): void {
  const snapshot = cache ?? [];
  listeners.forEach((listener) => {
    try {
      listener(snapshot);
    } catch {
      // 单个订阅者抛错不影响其他订阅者
    }
  });
}

export async function refreshMediaTasks(force = false): Promise<MediaTask[]> {
  if (inflight) return inflight;
  if (cache !== null && !force) return cache;
  inflight = request<{ tasks: MediaTask[] }>("/media/tasks?status=all&limit=100")
    .then((data) => {
      cache = data.tasks ?? [];
      notify();
      ensurePolling();
      return cache;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

function ensurePolling(): void {
  // 事件流正常时几乎用不上轮询；这里是断线兜底（035 §9.3）
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    if (needsPolling()) void refreshMediaTasks(true);
  }, 5000);
}

function bindEvents(): void {
  if (eventBound) return;
  eventBound = true;
  subscribeAppEvent("media_tasks_changed", () => {
    void refreshMediaTasks(true);
  });
}

/**
 * 订阅任务列表变化；首次订阅时拉一次全量。
 *
 * **新订阅者必须先拿到现有快照**：`refreshMediaTasks()` 命中 cache 时直接返回、
 * 不触发 notify（这是有意的去抖），于是后挂载的页面（点开「生成任务」）
 * 既拿不到快照也等不到通知，列表一直是空的——只有整页刷新重建 store 才正常
 * （2026-11-04 用户反馈实锤）。
 */
export function subscribeMediaTasks(listener: Listener): () => void {
  bindEvents();
  listeners.add(listener);
  if (cache !== null) listener(cache);
  void refreshMediaTasks();
  return () => {
    listeners.delete(listener);
  };
}

export function getTask(taskId: string): MediaTask | undefined {
  return (cache ?? []).find((task) => task.id === taskId);
}

/** 「不再等待」：本地隐藏，轮询继续，云端跑完仍可取回（035 §9.2）。 */
export async function dismissMediaTask(taskId: string): Promise<void> {
  await request(`/media/tasks/${taskId}/dismiss`, { method: "POST" });
  await refreshMediaTasks(true);
}

/** 播放用 URL：走 Range 流式端点（035 §8.3 播放与下载分流）。 */
export function mediaStreamUrl(path: string): string {
  return `${API_BASE}/files/media?path=${encodeURIComponent(path)}`;
}

// ---------------------------------------------------------------------------
// 完成通知（035 §9.4）：AppLayout 启动时调用一次。
// 只在「running → 终态」的**跳变**时提示，避免每次刷新都弹一遍。
// ---------------------------------------------------------------------------

const prevStatuses = new Map<string, string>();
let notificationsBound = false;

export function startMediaTaskNotifications(): void {
  if (notificationsBound) return;
  notificationsBound = true;
  subscribeMediaTasks((tasks) => {
    for (const task of tasks) {
      const previous = prevStatuses.get(task.id);
      prevStatuses.set(task.id, task.status);
      if (previous === task.status) continue;
      if (previous !== "queued" && previous !== "running") continue;
      if (task.status === "succeeded") {
        toast.success(i18next.t("tool.videoTaskDoneToast", "视频已生成"));
        void notifyTaskFinished(task.id, task.prompt || "视频生成", true);
      } else if (task.status === "failed" || task.status === "expired") {
        toast.error(
          task.error ?? i18next.t("tool.videoTaskFailed", "视频生成失败，请在「生成任务」面板重试"),
        );
        void notifyTaskFinished(task.id, task.prompt || "视频生成", false);
      }
    }
  });
}
