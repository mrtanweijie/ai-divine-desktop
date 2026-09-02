import type { ScheduledTask } from "@/types";
import i18next from "@/i18n";
import { pad } from "@/utils";

export function weekdayLabels(): string[] {
  return [
    i18next.t("tasks.weekday.monday", "周一"),
    i18next.t("tasks.weekday.tuesday", "周二"),
    i18next.t("tasks.weekday.wednesday", "周三"),
    i18next.t("tasks.weekday.thursday", "周四"),
    i18next.t("tasks.weekday.friday", "周五"),
    i18next.t("tasks.weekday.saturday", "周六"),
    i18next.t("tasks.weekday.sunday", "周日"),
  ];
}

export function weekdayText(days: number[]): string {
  const labels = weekdayLabels();
  const sorted = [...days].sort();
  if (
    sorted.length === 5 &&
    JSON.stringify(sorted) === JSON.stringify([1, 2, 3, 4, 5])
  ) {
    return i18next.t("tasks.workday", "工作日");
  }
  if (sorted.length === 1) {
    return labels[sorted[0]] ?? i18next.t("tasks.weekly", "每周");
  }
  if (sorted.length === 7) return i18next.t("tasks.everyday", "每天");
  return (
    sorted
      .map((day) => labels[day])
      .filter(Boolean)
      .join(i18next.t("tasks.dayJoin", "、")) || i18next.t("tasks.weekly", "每周")
  );
}

export function formatTaskSchedule(task: ScheduledTask): string {
  const hhmm = `${pad(task.run_hour ?? 8)}:${pad(task.run_minute ?? 0)}`;
  if (task.frequency === "once") {
    return task.run_at
      ? formatDateTime(task.run_at)
      : i18next.t("tasks.once", "一次性");
  }
  if (task.frequency === "interval") {
    const minutes = task.interval_minutes;
    if (!minutes) return i18next.t("tasks.periodicReminder", "周期提醒");
    if (minutes % 1440 === 0)
      return i18next.t("tasks.everyDays", "每 {{count}} 天", {
        count: minutes / 1440,
      });
    if (minutes % 60 === 0)
      return i18next.t("tasks.everyHours", "每 {{count}} 小时", {
        count: minutes / 60,
      });
    return i18next.t("tasks.everyMinutes", "每 {{count}} 分钟", {
      count: minutes,
    });
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
  return i18next.t("tasks.dateTime", "{{month}}月{{day}}日 {{time}}", {
    month: date.getMonth() + 1,
    day: date.getDate(),
    time: `${pad(date.getHours())}:${pad(date.getMinutes())}`,
  });
}

export function toLocalInputValue(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate()
  )}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
