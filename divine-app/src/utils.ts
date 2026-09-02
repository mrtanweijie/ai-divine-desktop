import i18next from "@/i18n";

export function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const locale = i18next.language || "zh-CN";
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startYesterday = new Date(startToday);
  startYesterday.setDate(startYesterday.getDate() - 1);
  const startDayBefore = new Date(startToday);
  startDayBefore.setDate(startDayBefore.getDate() - 2);
  const hhmm = date.toLocaleTimeString(locale, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  if (date >= startToday) return hhmm; // 今天：只显时分
  if (date >= startYesterday)
    return `${i18next.t("time.yesterday", "昨天")} ${hhmm}`; // 昨天
  if (date >= startDayBefore)
    return `${i18next.t("time.dayBefore", "前天")} ${hhmm}`; // 前天
  return date.toLocaleDateString(locale, {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }); // 更早：月日+时分
}

export function formatSize(bytes: number | undefined): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** 千/百万级别 token 展示：999 → "999"，2300 → "2.3k"，12.3 万 → "123k"，130 万 → "1.3m"。 */
export function formatTokens(count: number): string {
  if (count < 1000) return String(Math.round(count));
  const unit = count < 1_000_000 ? 1000 : 1_000_000;
  const suffix = count < 1_000_000 ? "k" : "m";
  const value = count / unit;
  const text =
    value >= 100 ? String(Math.round(value)) : value.toFixed(1).replace(/\.0$/, "");
  return `${text}${suffix}`;
}

/** 数字补零到两位：3 → "03"。 */
export function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
}
