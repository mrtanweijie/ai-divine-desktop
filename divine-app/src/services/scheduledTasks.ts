import { invoke } from "@tauri-apps/api/core";
import {
  isPermissionGranted,
  pending,
  requestPermission,
  Schedule,
  ScheduleEvery,
  sendNotification,
  cancel,
} from "@tauri-apps/plugin-notification";
import { request } from "@/services/request";
import { isMacosDesktop, isTauri } from "@/services/tauri";
import { storageGetRaw, storageSet, storageSetRaw } from "@/services/storage";
import type { CalendarEvent, ScheduledTask } from "@/types";
import i18next from "@/i18n";

type Listener = () => void;

const taskListeners = new Set<Listener>();
const eventListeners = new Set<Listener>();
let calendarSyncInFlight: Promise<void> | null = null;

export function subscribeTasksChanged(callback: Listener): () => void {
  taskListeners.add(callback);
  return () => taskListeners.delete(callback);
}

export function subscribeEventsChanged(callback: Listener): () => void {
  eventListeners.add(callback);
  return () => eventListeners.delete(callback);
}

export function emitTasksChanged(): void {
  taskListeners.forEach((callback) => callback());
}

export function emitEventsChanged(): void {
  eventListeners.forEach((callback) => callback());
}

export function listScheduledTasks(): Promise<{ tasks: ScheduledTask[] }> {
  return request("/scheduled-tasks");
}

export function createScheduledTask(
  body: Partial<ScheduledTask> & { title: string },
): Promise<ScheduledTask> {
  return request("/scheduled-tasks", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateScheduledTask(
  id: string,
  body: Partial<ScheduledTask>,
): Promise<ScheduledTask> {
  return request(`/scheduled-tasks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteScheduledTask(id: string): Promise<void> {
  return request(`/scheduled-tasks/${id}`, { method: "DELETE" });
}

export function listCalendarEvents(): Promise<{ events: CalendarEvent[] }> {
  return request("/calendar-events");
}

export function createCalendarEvent(
  body: Partial<CalendarEvent> & { title: string; start_at: string },
): Promise<CalendarEvent> {
  return request("/calendar-events", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateCalendarEvent(
  id: string,
  body: Partial<CalendarEvent>,
): Promise<CalendarEvent> {
  return request(`/calendar-events/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteCalendarEvent(id: string): Promise<void> {
  return request(`/calendar-events/${id}`, { method: "DELETE" });
}

export function notificationId(id: string): number {
  const hex = id.replace(/-/g, "").slice(0, 8);
  const parsed = parseInt(hex, 16);
  return Number.isNaN(parsed) ? 0 : parsed & 0x7fffffff;
}

function webNotificationPermission(): NotificationPermission | null {
  if (typeof window === "undefined" || !("Notification" in window)) return null;
  return window.Notification.permission;
}

let nativePermissionCache: boolean | null = null;

async function requestNativeNotificationPermission(): Promise<boolean | null> {
  if (!isMacosDesktop()) return null;
  try {
    const granted = await invoke<boolean>("request_notification_permission");
    nativePermissionCache = granted;
    return granted;
  } catch (error) {
    console.warn("[notifications] native permission request failed", error);
    return null;
  }
}

async function showNativeNotification(title: string, body: string): Promise<boolean> {
  if (!isMacosDesktop()) return false;
  try {
    await invoke("show_native_notification", { title, body });
    return true;
  } catch (error) {
    console.warn("[notifications] native notification failed", error);
    return false;
  }
}

export async function isNotificationGranted(): Promise<boolean> {
  if (!isTauri()) return true;
  if (isMacosDesktop()) {
    const native = await requestNativeNotificationPermission();
    if (native !== null) return native;
    // 原生通道不可用（例如 dev 裸二进制）：不显示误导性的“未开启”提示。
    return true;
  }
  const webPermission = webNotificationPermission();
  if (webPermission === "granted") return true;
  if (webPermission === "denied") return false;
  try {
    return await isPermissionGranted();
  } catch {
    return false;
  }
}

export async function ensureNotificationPermission(): Promise<boolean> {
  if (!isTauri()) return true;
  if (isMacosDesktop()) {
    const native = await requestNativeNotificationPermission();
    if (native !== null) return native;
    return true;
  }
  const webPermission = webNotificationPermission();
  if (webPermission === "granted") return true;
  if (webPermission === "denied") return false;
  try {
    if (webPermission === "default") {
      return (await requestPermission()) === "granted";
    }
    return await isPermissionGranted();
  } catch {
    return false;
  }
}

const REMINDER_SEEN_PREFIX = "divine:reminder-seen:";
const REMINDER_LOOKBACK_MS = 10 * 60 * 1000;
let reminderPollTimer: ReturnType<typeof setInterval> | null = null;
const seenReminderRuns = new Set<string>();

function reminderSeenAt(taskId: string): string | null {
  return storageGetRaw(`${REMINDER_SEEN_PREFIX}${taskId}`);
}

function markReminderSeen(taskId: string, lastRunAt: string): void {
  seenReminderRuns.add(`${taskId}:${lastRunAt}`);
  storageSetRaw(`${REMINDER_SEEN_PREFIX}${taskId}`, lastRunAt);
}

export async function notifyDueReminders(tasks: ScheduledTask[]): Promise<number> {
  if (!isTauri()) return 0;
  const nativeAvailable = isMacosDesktop() && nativePermissionCache === true;
  if (!nativeAvailable && webNotificationPermission() !== "granted") return 0;
  const now = Date.now();
  let shown = 0;
  for (const task of tasks) {
    if (task.status !== "active" || task.task_type !== "reminder") continue;
    if (!task.last_run_at) continue;
    const runAt = Date.parse(task.last_run_at);
    if (Number.isNaN(runAt) || runAt < now - REMINDER_LOOKBACK_MS) continue;
    if (reminderSeenAt(task.id) === task.last_run_at) continue;
    const runKey = `${task.id}:${task.last_run_at}`;
    if (seenReminderRuns.has(runKey)) continue;
    const title = task.title;
    const body = task.description || task.title;
    const nativeShown = await showNativeNotification(title, body);
    if (nativeShown) {
      markReminderSeen(task.id, task.last_run_at);
      shown++;
      continue;
    }
    try {
      new window.Notification(title, {
        body,
        tag: `divine-task-${task.id}`,
      });
      markReminderSeen(task.id, task.last_run_at);
      shown++;
    } catch (error) {
      console.warn("[notifications] failed to show reminder", error);
    }
  }
  return shown;
}

function pluginWeekday(day: number): number {
  // 本地 0=周一 ... 6=周日，插件 1=周日 ... 7=周六
  return day === 6 ? 1 : day + 2;
}

interface NotificationPlan {
  id: number;
  schedule: Schedule;
}

function taskNotificationPlans(task: ScheduledTask): NotificationPlan[] {
  const base = notificationId(task.id);
  const hour = task.run_hour ?? 8;
  const minute = task.run_minute ?? 0;
  if (task.frequency === "once") {
    const date = new Date(task.next_run_at ?? task.run_at ?? "");
    if (Number.isNaN(date.getTime())) return [];
    return [{ id: base, schedule: Schedule.at(date, false) }];
  }
  if (task.frequency === "interval" && task.interval_minutes) {
    return [
      {
        id: base,
        schedule: Schedule.every(ScheduleEvery.Minute, task.interval_minutes),
      },
    ];
  }
  if (task.frequency === "daily") {
    return [
      {
        id: base,
        schedule: Schedule.interval({ hour, minute }),
      },
    ];
  }
  if (task.frequency === "weekly") {
    const days = task.days_of_week ?? [];
    return days.map((day) => ({
      id: (base + day * 1009) & 0x7fffffff,
      schedule: Schedule.interval({
        weekday: pluginWeekday(day),
        hour,
        minute,
      }),
    }));
  }
  if (task.frequency === "monthly") {
    return [
      {
        id: base,
        schedule: Schedule.interval({
          day: task.day_of_month ?? 1,
          hour,
          minute,
        }),
      },
    ];
  }
  return [];
}

export async function syncTaskNotifications(
  tasks: ScheduledTask[],
): Promise<{ scheduled: number; cancelled: number }> {
  if (!isTauri()) return { scheduled: 0, cancelled: 0 };
  storageSet("divine:notification-debug", {
    hasNotification: typeof window !== "undefined" && "Notification" in window,
    permission:
      typeof window !== "undefined" && "Notification" in window
        ? window.Notification.permission
        : null,
    isMacosDesktop: isMacosDesktop(),
    nativePermission: nativePermissionCache,
    time: new Date().toISOString(),
  });
  if (isMacosDesktop()) {
    // The Tauri plugin cannot schedule desktop notifications, so macOS shows
    // them from the frontend as soon as the sidecar advances a reminder.
    return { scheduled: await notifyDueReminders(tasks), cancelled: 0 };
  }
  try {
    const existing = await pending();
    const existingIds = new Set(existing.map((notification) => notification.id));
    const wantedIds = new Set<number>();
    let scheduled = 0;
    for (const task of tasks) {
      if (task.status !== "active") continue;
      for (const plan of taskNotificationPlans(task)) {
        wantedIds.add(plan.id);
        if (existingIds.has(plan.id)) continue;
        sendNotification({
          id: plan.id,
          title: task.title,
          body: task.description || i18next.t("tasks.reminderBody", "定时任务提醒"),
          schedule: plan.schedule,
          group: "divine-scheduled-tasks",
        });
        scheduled++;
      }
    }
    const stale = [...existingIds].filter((id) => !wantedIds.has(id));
    if (stale.length > 0) {
      await cancel(stale);
    }
    return { scheduled, cancelled: stale.length };
  } catch (error) {
    console.warn("[notifications] sync failed", error);
    return { scheduled: 0, cancelled: 0 };
  }
}

export async function syncActiveTaskNotifications(): Promise<void> {
  if (!isTauri()) return;
  try {
    const { tasks } = await listScheduledTasks();
    await syncTaskNotifications(tasks);
  } catch (error) {
    console.warn("[notifications] startup sync failed", error);
  }
}

export function startTaskReminderPolling(): () => void {
  if (!isTauri()) return () => undefined;
  if (reminderPollTimer !== null) return () => undefined;

  const poll = async () => {
    try {
      const granted = await ensureNotificationPermission();
      storageSet("divine:notification-debug", {
        hasNotification: typeof window !== "undefined" && "Notification" in window,
        permission:
          typeof window !== "undefined" && "Notification" in window
            ? window.Notification.permission
            : null,
        granted,
        nativePermission: nativePermissionCache,
        time: new Date().toISOString(),
      });
      const { tasks } = await listScheduledTasks();
      await syncTaskNotifications(tasks);
    } catch (error) {
      console.warn("[notifications] poll failed", error);
    }
  };

  void poll();
  reminderPollTimer = window.setInterval(() => void poll(), 10_000);
  return () => {
    if (reminderPollTimer !== null) {
      window.clearInterval(reminderPollTimer);
      reminderPollTimer = null;
    }
  };
}

export async function syncCalendarToSystem(
  events: CalendarEvent[],
  onError?: (message: string) => void,
): Promise<void> {
  if (!isTauri()) return;
  if (calendarSyncInFlight) return calendarSyncInFlight;
  calendarSyncInFlight = (async () => {
    for (const event of events) {
      if (event.synced) continue;
      try {
        const uid = await invoke<string>("add_calendar_event", {
          title: event.title,
          startAt: event.start_at,
          endAt: event.end_at ?? "",
          notes: event.notes,
        });
        await updateCalendarEvent(event.id, {
          system_event_id: uid,
          synced: 1,
        });
        emitEventsChanged();
      } catch (error) {
        onError?.(error instanceof Error ? error.message : String(error));
      }
    }
  })().finally(() => {
    calendarSyncInFlight = null;
  });
  return calendarSyncInFlight;
}

export async function removeSystemCalendarEvent(event: CalendarEvent): Promise<void> {
  if (!isTauri()) return;
  try {
    await invoke<string>("remove_calendar_event", {
      title: event.title,
      startAt: event.start_at,
    });
  } catch {
    // 系统日历删除失败不影响应用内日程
  }
}
