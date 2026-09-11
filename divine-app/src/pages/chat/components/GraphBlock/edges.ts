/**
 * edges —— 边族：双层边（静态底线 + 流动层）+ 箭头 + antline/pulse。
 *
 * 核心约定（020 §5.2）：底线讲拓扑（中性色、常驻），流动层讲动态（tone 色、可关）。
 * **两层叠加而不是替换**——关动画、历史回放、导出时图都完整可读。
 */

import type { GraphEdge, GraphTone } from "./GraphIR";
import { type GraphThemeName } from "./graphTheme";
import { toneColor } from "./graphTones";
import { type EdgeSpec } from "./presets";

/** 流动层 dasharray 与周期（020 §5.2：speed 0.5/1/2 → 2.2s/1.1s/0.58s）。 */
const FLOW_DASH = "6 7";
const FLOW_DURATION = (speed: number) => 1.1 / (speed || 1);

/** 线型 → stroke-dasharray（实线 / 虚线 / 点线）。 */
export function dashArray(style: GraphEdge["style"]): string | undefined {
  if (style === "dashed") return "5 4";
  if (style === "dotted") return "1.5 4";
  return undefined;
}

/** 箭头 marker 名（defs 里注册；色随线色）。 */
export function markerName(arrow: EdgeSpec["arrow"], tone: GraphTone, kind: string): string {
  return `graph-arrow-${arrow}-${tone}-${kind}`;
}

/**
 * 注入 antline 的 keyframes（模块加载时一次）。
 * X6 的流动层是 SVG path，用 CSS 动画驱动 stroke-dashoffset 最省。
 */
export function ensureFlowKeyframes(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById("graph-keyframes")) return;
  const style = document.createElement("style");
  style.id = "graph-keyframes";
  style.textContent = "@keyframes graph-dash{to{stroke-dashoffset:-13}}";
  document.head.appendChild(style);
}

/** 底线的 attrs（中性、常驻）。 */
export function baseLineAttrs(
  edge: GraphEdge,
  spec: EdgeSpec,
  themeName: GraphThemeName,
  theme: { line: string },
): Record<string, unknown> {
  const attrs: Record<string, unknown> = {
    stroke: theme.line,
    strokeWidth: 1.25,
    strokeDasharray: dashArray(edge.style),
    strokeLinejoin: "round",
    strokeLinecap: "round",
  };
  if (spec.arrow !== "none") {
    attrs.targetMarker = {
      name: spec.arrow === "hollow" ? "block" : "block",
      width: 8,
      height: 7,
      fill: edge.tone && edge.tone !== "neutral" ? toneColor(edge.tone, themeName) : theme.line,
    };
  }
  return attrs;
}

/** 流动层 attrs（tone 色、可关）。无 flow 声明时返回 null。 */
export function flowAttrs(
  edge: GraphEdge,
  themeName: GraphThemeName,
): Record<string, unknown> | null {
  if (!edge.flow) return null;
  const tone: GraphTone = edge.flow.tone ?? edge.tone ?? "info";
  const speed = edge.flow.speed ?? 1;
  if (edge.flow.mode === "pulse") {
    return {
      stroke: toneColor(tone, themeName),
      strokeWidth: 3,
      strokeDasharray: "1 26",
      strokeLinecap: "round",
      style: { animation: `graph-dash ${FLOW_DURATION(speed) * 1.6}s linear infinite` },
    };
  }
  return {
    stroke: toneColor(tone, themeName),
    strokeWidth: 1.5,
    strokeDasharray: FLOW_DASH,
    strokeLinecap: "butt",
    style: { animation: `graph-dash ${FLOW_DURATION(speed)}s linear infinite` },
  };
}

/**
 * 边标签的显示文本：UML `事件[守卫]` 的守卫段用等宽字体降级（state 场景）。
 * 渲染器按 `labelParts` 分别设置 attrs。
 */
export function labelParts(label?: string): { event: string; guard: string } | null {
  if (!label) return null;
  const match = /^(.*?)\s*\[\s*([^\]]*?)\s*\]\s*$/.exec(label);
  if (!match) return { event: label, guard: "" };
  return { event: match[1], guard: match[2] };
}
