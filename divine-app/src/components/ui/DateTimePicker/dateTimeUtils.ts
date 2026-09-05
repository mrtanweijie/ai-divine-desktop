// Date/time formatting helpers shared by the picker and calendar panel.
import i18next from "@/i18n";
import { pad } from "@/utils";

export const HOURS = Array.from({ length: 24 }, (_, index) => index);
export const MINUTES = Array.from({ length: 12 }, (_, index) => index * 5);

export function parseValue(value: string): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDisplay(date: Date | null): string {
  if (!date) return i18next.t("time.pickDateTime", "选择日期和时间");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate(),
  )} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}
