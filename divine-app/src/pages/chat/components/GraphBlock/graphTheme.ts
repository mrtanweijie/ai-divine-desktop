/**
 * graphTheme —— 画布基色的 JS 侧派生（表面 / 线 / 文字）。
 *
 * 分工（与 MEMORY 定稿一致）：
 * - `uiPalette.ts` 的 `UI_COLORS` 负责「底与字」，与 `styles/index.less` 的 CSS token 同源；
 * - `graphTones.ts` 负责「主色调」（语义色 / 分支色）。
 *
 * X6 的 attrs 需要真实色值（P0 第 3 条要实测能否直接用 CSS 变量），
 * 因此这里把 UI_COLORS 翻译成渲染器可直接吃的常量。
 */

import { UI_COLORS } from "@/styles/uiPalette";

export type GraphThemeName = "dark" | "light";

export interface GraphTheme {
  /** 画布底色（导出 PNG 时作为 backgroundColor） */
  surface: string;
  surface2: string;
  /** 底线：静态拓扑层，常驻 */
  line: string;
  /** 强调底线：hover 关联高亮时提亮到这一档（020 §11.2） */
  lineStrong: string;
  /** 节点描边（默认态） */
  border: string;
  borderStrong: string;
  text: string;
  textSecondary: string;
  textMuted: string;
  accent: string;
  /** 边标签底衬 / 分组填充 */
  labelBg: string;
  clusterFill: string;
  clusterStroke: string;
  laneFill: string;
}

/**
 * 线的两档在 UI_COLORS 里没有对应 token（图表/图形专用），
 * 按主题对比度单独定档：dark 用中性灰阶、light 用浅灰阶，
 * 都保证在 surface 上 ≥ 3:1（WCAG 1.4.11 非文本图形元素）。
 */
const LINE_COLORS: Record<GraphThemeName, { line: string; strong: string }> = {
  dark: { line: "#39414b", strong: "#5c6673" },
  light: { line: "#d5dae1", strong: "#a9b2bd" },
};

const CLUSTER_COLORS: Record<GraphThemeName, { fill: string; stroke: string; lane: string }> = {
  dark: {
    fill: "rgba(255,255,255,0.022)",
    stroke: "rgba(255,255,255,0.10)",
    lane: "rgba(255,255,255,0.016)",
  },
  light: {
    fill: "rgba(15,23,42,0.018)",
    stroke: "rgba(15,23,42,0.12)",
    lane: "rgba(15,23,42,0.022)",
  },
};

export function graphTheme(theme: GraphThemeName): GraphTheme {
  const base = UI_COLORS[theme];
  const lines = LINE_COLORS[theme];
  const clusters = CLUSTER_COLORS[theme];
  return {
    surface: base.surface,
    surface2: base.surface2,
    line: lines.line,
    lineStrong: lines.strong,
    border: base.surface2,
    borderStrong: theme === "dark" ? "#343a44" : "#cbd5e1",
    text: base.text,
    textSecondary: base.textSecondary,
    textMuted: base.textMuted,
    accent: theme === "dark" ? "#61A7D0" : "#036EAD",
    labelBg: base.surface,
    clusterFill: clusters.fill,
    clusterStroke: clusters.stroke,
    laneFill: clusters.lane,
  };
}

/** 与 MermaidBlock / 图表一致的字体栈。 */
export const GRAPH_FONT_STACK =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif';
export const GRAPH_MONO_STACK =
  'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace';
