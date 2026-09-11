/**
 * icons —— 全部内联 SVG path（**没有任何 URL / 外链图片**）。
 *
 * 为什么不用外链图标（004 决策 7）：
 * - 本地优先 / 隐私可控：外链请求会泄漏用户在看什么图；
 * - 导出后失效：`toSVG/toPNG` 产出里外链就是裂图。
 *
 * 统一 16×16 视框，由调用方 translate 到目标位置，`stroke-width 1.5`，
 * 走 `stroke` 描边、`fill: none`（线性图标风格，与项目 lucide 图标一致）。
 */

/** dag：8 个任务图标。 */
export const TASK_ICONS: Record<string, string> = {
  code: "M5 4 L1.5 8 L5 12 M11 4 L14.5 8 L11 12",
  box: "M2 5.5 L8 2 L14 5.5 L14 10.5 L8 14 L2 10.5 Z M2 5.5 L8 9 L14 5.5 M8 9 L8 14",
  check: "M3 8.5 L6.5 12 L13 4.5",
  flask:
    "M6 2 L6 6.5 L2.5 12.5 A1 1 0 0 0 3.4 14 L12.6 14 A1 1 0 0 0 13.5 12.5 L10 6.5 L10 2 M5 2 L11 2",
  stack: "M8 2 L14 5 L8 8 L2 5 Z M2 8 L8 11 L14 8 M2 11 L8 14 L14 11",
  layers: "M8 2 L14 5.5 L8 9 L2 5.5 Z M2 9.5 L8 13 L14 9.5",
  upload: "M8 12 L8 3 M4.5 6.5 L8 3 L11.5 6.5 M3 13.5 L13 13.5",
  gear: "M8 6 A2 2 0 1 0 8 10 A2 2 0 1 0 8 6 M8 1.5 L8 3.5 M8 12.5 L8 14.5 M1.5 8 L3.5 8 M12.5 8 L14.5 8 M3.4 3.4 L4.8 4.8 M11.2 11.2 L12.6 12.6 M12.6 3.4 L11.2 4.8 M4.8 11.2 L3.4 12.6",
};

/** dataflow：6 类加工类型的图标。 */
export const FLOW_ICONS: Record<string, string> = {
  INPUT: "M2 4 L9 4 L14 8 L9 12 L2 12 Z",
  FILTER: "M2 3 L14 3 L9 8.5 L9 13 L7 11.5 L7 8.5 Z",
  JOIN: "M2 4 L7 8 L2 12 M14 4 L9 8 L14 12 M7 8 L9 8",
  UNION: "M3 3 L3 13 M6 3 L6 13 M10 8 L14 8 M6 8 L10 8 M11.5 5.5 L14 8 L11.5 10.5",
  AGG: "M3 3 L13 3 L3 13 L13 13",
  OUTPUT: "M2 4 L9 4 L14 8 L9 12 L2 12 Z M9 8 L15 8",
};

/** arch：6 类架构角色图标。 */
export const ARCH_ICONS: Record<string, string> = {
  external: "M2 3 L14 3 L14 10 L8 10 L8 13 L12 13 M1 13 L6 13 M8 6.5 L11 6.5",
  security: "M8 2 L13.5 4.5 L13.5 8 C13.5 11.5 8 14 8 14 C8 14 2.5 11.5 2.5 8 L2.5 4.5 Z",
  cloud: "M4.5 12.5 A3 3 0 0 1 4.5 6.5 A3.5 3.5 0 0 1 11.5 6.5 A3 3 0 0 1 11.5 12.5 Z",
  backend: "M8 2 L14 5.5 L14 10.5 L8 14 L2 10.5 L2 5.5 Z M2 5.5 L8 9 L14 5.5 M8 9 L8 14",
  database:
    "M8 2 C11.3 2 14 3.1 14 4.5 C14 5.9 11.3 7 8 7 C4.7 7 2 5.9 2 4.5 C2 3.1 4.7 2 8 2 M2 4.5 L2 11.5 C2 12.9 4.7 14 8 14 C11.3 14 14 12.9 14 11.5 L14 4.5 M2 8 C2 9.4 4.7 10.5 8 10.5 C11.3 10.5 14 9.4 14 8",
  messagebus: "M2 4 L14 4 L14 12 L2 12 Z M2 4.5 L8 9 L14 4.5",
};

/** concept：5 类实体类型图标。 */
export const CONCEPT_ICONS: Record<string, string> = {
  module: "M3 3 L13 3 L13 13 L3 13 Z M3 6.5 L13 6.5 M6.5 6.5 L6.5 13",
  tech: "M6 12 L10 12 M6.5 14 L9.5 14 M4.5 3.5 L11.5 3.5 A4 4 0 0 1 8 10.5 A4 4 0 0 1 4.5 3.5",
  data: "M4 4 C4 2.9 11.1 2.9 11.1 4 C11.1 5.1 4 5.1 4 4 M4 4 L4 12 C4 13.1 11.1 13.1 11.1 12 L11.1 4",
  process: "M3 8 L6 8 L6 5 L11 5 M11 5 L13 5 L13 12 L4 12 L4 10",
  concept:
    "M8 3 A3 3 0 0 1 8 9 A3 3 0 0 1 8 3 M5 13.5 L11 13.5 M6.5 11 L6.5 13.5 M9.5 11 L9.5 13.5",
};

/** 状态徽标 4 态：d 画在 14×14 坐标系内。 */
export const STATUS_MARKS: Record<string, string> = {
  running: "",
  pending: "M2 7 A5 5 0 1 1 12 7 A5 5 0 1 1 2 7",
  success: "M3.5 7.5 L6 10 L10.5 4.5",
  failed: "M4 4 L10 10 M10 4 L4 10",
};

/** 状态徽标描边色语义键（供 renderer 映射到 tone）。 */
export const STATUS_TONE: Record<string, string> = {
  pending: "neutral",
  running: "info",
  success: "success",
  failed: "error",
};

export function iconPath(kind: "task" | "flow" | "arch" | "concept", name?: string): string {
  if (!name) return "";
  const table =
    kind === "task"
      ? TASK_ICONS
      : kind === "flow"
        ? FLOW_ICONS
        : kind === "arch"
          ? ARCH_ICONS
          : CONCEPT_ICONS;
  return table[name] ?? "";
}
