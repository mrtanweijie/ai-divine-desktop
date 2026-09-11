/**
 * graphTones —— 交互图形的语义色常量（双主题）。
 *
 * **刻意独立于 `ChartBlock/chartOptions.ts`**：图表改色不应误伤图形，
 * 两套色板各自演进（020 §5.3 定稿）。唯一的"同源"是都取自项目色板体系。
 *
 * 关键收敛（020 §5.3）：`neutral` 与 `info` 视觉等同（中性灰描边），
 * 只有 `success / warning / error` 上语义色——默认态是一张干净的黑白图。
 * `info` 的蓝只出现在流动线上。
 */

import type { GraphTone } from "./GraphIR";

export interface TonePalette {
  neutral: string;
  info: string;
  success: string;
  warning: string;
  error: string;
}

/**
 * dark 档 `info = #61A7D0`，不复用图表色 `#036EAD`——
 * 后者在暗底亮度仅 35%，1px 描边看不见（020 §5.3）。
 */
export const GRAPH_TONES: Record<"dark" | "light", TonePalette> = {
  dark: {
    neutral: "#8A94A6",
    info: "#61A7D0",
    success: "#3FB98A",
    warning: "#F3962F",
    error: "#E07A82",
  },
  light: {
    neutral: "#7A8494",
    info: "#036EAD",
    success: "#2F9E6E",
    warning: "#C77F1E",
    error: "#C9525B",
  },
};

/** 只有这三档做底色微染，其余保持透明（默认态是黑白图）。 */
export const TINTED_TONES: ReadonlySet<GraphTone> = new Set<GraphTone>([
  "success",
  "warning",
  "error",
]);

/** 语义底色微染强度（020 §5.6 / §11.1 定稿 8%）。 */
export const TONE_TINT_OPACITY = 0.08;

/** hover 时 tint 提到 14%（020 §11.2 节点六态）。 */
export const TONE_TINT_HOVER_OPACITY = 0.14;

/**
 * 分支色（mindmap / 类别色带）——5 档，取自图表定性色板。
 * **由前端按分支（或类别）首次出现顺序分配，IR 里不写**（020 §5.6）。
 */
export const BRANCH_COLORS: Record<"dark" | "light", readonly string[]> = {
  light: ["#F3962F", "#036EAD", "#DD656D", "#506AAA", "#728DC1"],
  dark: ["#FACC8F", "#61A7D0", "#E17692", "#F3962F", "#728DC1"],
};

/** tone 的中文语义：无障碍 aria-label 用（020 §11.5）。 */
export const TONE_LABELS: Record<GraphTone, string> = {
  neutral: "",
  info: "进行中",
  success: "成功",
  warning: "需注意",
  error: "异常",
};

export function toneColor(tone: GraphTone, theme: "dark" | "light"): string {
  return GRAPH_TONES[theme][tone];
}

export function branchColor(index: number, theme: "dark" | "light"): string {
  const palette = BRANCH_COLORS[theme];
  return palette[index % palette.length];
}

/** 是否为"上色"的 tone（决定节点描边是否换色、是否给 tint）。 */
export function isTinted(tone: GraphTone): boolean {
  return TINTED_TONES.has(tone);
}

/**
 * 按类别（或分支）首次出现顺序分配色索引——IR 只给名字，色由这里定，
 * 且同一张图里同类永远同色（020 §5.9）。
 */
export function assignColorIndexes(names: string[], limit = 5): Map<string, number> {
  const assigned = new Map<string, number>();
  for (const name of names) {
    if (assigned.has(name)) continue;
    const next = assigned.size;
    if (next >= limit) continue; // 超出上限的类别不着色
    assigned.set(name, next);
  }
  return assigned;
}
