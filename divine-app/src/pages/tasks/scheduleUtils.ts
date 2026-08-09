import type { ScheduledTask } from "@/types";

export const WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

export function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function weekdayText(days: number[]): string {
  const sorted = [...days].sort();
  if (
    sorted.length === 5 &&
    JSON.stringify(sorted) === JSON.stringify([1, 2, 3, 4, 5])
  ) {
    return "工作日";
  }
  if (sorted.length === 1) {
    return WEEKDAYS[sorted[0]] ?? "每周";
  }
  if (sorted.length === 7) return "每天";
  return sorted.map((day) => WEEKDAYS[day]).filter(Boolean).join("、") || "每周";
}

export function formatTaskSchedule(task: ScheduledTask): string {
  const hhmm = `${pad(task.run_hour ?? 8)}:${pad(task.run_minute ?? 0)}`;
  if (task.frequency === "once") {
    return task.run_at ? formatDateTime(task.run_at) : "一次性";
  }
  if (task.frequency === "interval") {
    const minutes = task.interval_minutes;
    if (!minutes) return "周期提醒";
    if (minutes % 1440 === 0) return `每 ${minutes / 1440} 天`;
    if (minutes % 60 === 0) return `每 ${minutes / 60} 小时`;
    return `每 ${minutes} 分钟`;
  }
  if (task.frequency === "daily") return `${weekdayText(task.days_of_week)} ${hhmm}`;
  if (task.frequency === "weekly") return `${weekdayText(task.days_of_week)} ${hhmm}`;
  if (task.frequency === "monthly") return `每月 ${task.day_of_month} 日 ${hhmm}`;
  return hhmm;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getMonth() + 1}月${date.getDate()}日 ${pad(date.getHours())}:${pad(
    date.getMinutes()
  )}`;
}

export function toLocalInputValue(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate()
  )}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
