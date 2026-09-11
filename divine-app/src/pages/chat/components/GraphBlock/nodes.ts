/**
 * nodes —— X6 节点形态族注册（纯 SVG markup）。
 *
 * 两条硬约束（004 决策 6）：
 * 1. **禁用 `@antv/x6-react-shape` 与一切 HTML 节点**——React 节点渲染进
 *    `foreignObject`，WKWebView 下 `toPNG` 极易失败、外联 CSS 导出即丢，
 *    而导出是硬需求。全部走纯 SVG markup。
 * 2. **统一三层结构 `body → tint → label`**：换形态不换配色逻辑，
 *    语义 tone 只改 tint 的 fillOpacity 与 body 的 stroke。
 *
 * X6 由调用方动态 import 后注入（保持 GraphBlock 的代码分块），
 * 因此本文件不出现顶层 `@antv/x6` import。
 */

import type { GraphNode, GraphTone } from "./GraphIR";
import { type GraphTheme, GRAPH_FONT_STACK, GRAPH_MONO_STACK } from "./graphTheme";
import { isTinted, toneColor } from "./graphTones";

/* eslint-disable @typescript-eslint/no-explicit-any -- X6 类型在动态 import 侧 */

/** 形态尺寸表（020 §5.1 / §5.5 / §5.6 / §5.7）。 */
export const SHAPE_SIZES: Record<string, [number, number]> = {
  pill: [112, 38],
  rounded: [136, 46],
  diamond: [124, 58],
  cylinder: [118, 58],
  section: [176, 92],
  milestone: [132, 52],
  stateNode: [152, 44],
  statePseudo: [30, 30],
  statePseudoFinal: [30, 30],
  statePseudoChoice: [30, 30],
  dagNode: [188, 40],
  dpNode: [212, 48],
  orgNode: [176, 56],
  conceptNode: [44, 44],
  archNode: [176, 52],
  mapRoot: [140, 46],
  mapBranch: [118, 34],
  mapLeaf: [96, 26],
};

/**
 * 形态 → 注册名。
 * 每个形态注册两种"语义皮肤"不需要：颜色由 renderer 按 tone 覆写 attrs，
 * 这里只给中性默认值。
 */
export const SHAPE_REGISTRY_PREFIX = "graph-";

/** 文本截断（中文字符按 1em、拉丁按 0.55em 估算宽度）。 */
export function truncateToWidth(text: string, maxPx: number, fontSize: number): string {
  if (!text) return "";
  const width = (ch: string) =>
    /[\u3000-\u9fff\uff00-\uffef]/.test(ch) ? fontSize : fontSize * 0.55;
  let used = 0;
  let out = "";
  for (const ch of text) {
    const next = used + width(ch);
    if (next > maxPx) return `${out}…`;
    out += ch;
    used = next;
  }
  return out;
}

function markupBody(shape: string, width: number, height: number, attrs: Record<string, unknown>) {
  switch (shape) {
    case "pill":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "text", selector: "label" },
      ];
    case "diamond": {
      const hw = width / 2;
      const hh = height / 2;
      attrs.body = {
        ...(attrs.body as object),
        points: `${hw},0 ${width},${hh} ${hw},${height} 0,${hh}`,
      };
      return [
        { tagName: "polygon", selector: "body" },
        { tagName: "text", selector: "label" },
      ];
    }
    case "cylinder":
      return [
        { tagName: "path", selector: "body" },
        { tagName: "ellipse", selector: "cap" },
        { tagName: "text", selector: "label" },
      ];
    case "section":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "path", selector: "divider" },
        { tagName: "text", selector: "label" },
        { tagName: "text", selector: "detail" },
      ];
    case "dagNode":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "path", selector: "icon" },
        { tagName: "text", selector: "label" },
        { tagName: "path", selector: "status" },
        { tagName: "circle", selector: "statusDot" },
      ];
    case "dpNode":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "rect", selector: "tile" },
        { tagName: "path", selector: "icon" },
        { tagName: "text", selector: "label" },
        { tagName: "text", selector: "sublabel" },
        { tagName: "path", selector: "status" },
        { tagName: "circle", selector: "statusDot" },
      ];
    case "stateNode":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "rect", selector: "accent" },
        { tagName: "text", selector: "label" },
        { tagName: "text", selector: "badge" },
      ];
    case "statePseudo":
    case "statePseudoFinal":
      return [
        { tagName: "circle", selector: "body" },
        { tagName: "circle", selector: "inner" },
      ];
    case "statePseudoChoice":
      return [{ tagName: "polygon", selector: "body" }];
    case "orgNode":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "rect", selector: "avatar" },
        { tagName: "text", selector: "initial" },
        { tagName: "text", selector: "label" },
        { tagName: "text", selector: "sublabel" },
        { tagName: "circle", selector: "foldBg" },
        { tagName: "text", selector: "foldText" },
      ];
    case "conceptNode":
      return [
        { tagName: "circle", selector: "body" },
        { tagName: "circle", selector: "tint" },
        { tagName: "path", selector: "icon" },
        { tagName: "text", selector: "label" },
      ];
    case "archNode":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "rect", selector: "tile" },
        { tagName: "path", selector: "icon" },
        { tagName: "text", selector: "label" },
        { tagName: "text", selector: "sublabel" },
        { tagName: "text", selector: "tag" },
      ];
    case "mapRoot":
    case "mapBranch":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "rect", selector: "bar" },
        { tagName: "text", selector: "label" },
      ];
    case "mapLeaf":
      return [
        { tagName: "text", selector: "label" },
        { tagName: "rect", selector: "baseline" },
      ];
    default:
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "text", selector: "label" },
      ];
  }
}

/** 形态的静态 attrs（尺寸相关的几何一律在这里算死，运行时只改颜色）。 */
function staticAttrs(shape: string, w: number, h: number) {
  const text = (extra: Record<string, unknown> = {}) => ({
    fill: "#000",
    fontSize: 13,
    fontWeight: 500,
    fontFamily: GRAPH_FONT_STACK,
    textAnchor: "middle",
    textVerticalAnchor: "middle",
    ...extra,
  });
  switch (shape) {
    case "pill":
      return {
        body: { width: w, height: h, rx: h / 2, ry: h / 2, strokeWidth: 1 },
        tint: { width: w, height: h, rx: h / 2, ry: h / 2, strokeWidth: 0, fillOpacity: 0 },
        label: text({
          x: w / 2,
          y: h / 2,
          textWrap: { width: -32, height: -16, ellipsis: true },
        }),
      };
    case "rounded":
      return {
        body: { width: w, height: h, rx: 8, ry: 8, strokeWidth: 1 },
        tint: { width: w, height: h, rx: 8, ry: 8, strokeWidth: 0, fillOpacity: 0 },
        label: text({
          x: w / 2,
          y: h / 2,
          textWrap: { width: -32, height: -16, ellipsis: true },
        }),
      };
    case "diamond":
      return {
        body: { strokeWidth: 1, strokeLinejoin: "round" },
        label: text({
          fontSize: 12,
          textWrap: { width: -52, height: -26, ellipsis: true },
        }),
      };
    case "cylinder": {
      const rx = w / 2;
      const ry = 7;
      const d = `M0,${ry} A${rx},${ry} 0 0 1 ${w},${ry} L${w},${h - ry} A${rx},${ry} 0 0 1 0,${h - ry} Z`;
      return {
        body: { d, strokeWidth: 1 },
        cap: { cx: rx, cy: ry, rx, ry, strokeWidth: 1 },
        label: text({
          x: rx,
          y: h / 2 + 2,
          fontSize: 12,
          textWrap: { width: -28, height: -20, ellipsis: true },
        }),
      };
    }
    case "section": {
      const headHeight = 30;
      return {
        body: { width: w, height: h, rx: 8, ry: 8, strokeWidth: 1 },
        divider: { d: `M0,${headHeight} L${w},${headHeight}`, strokeWidth: 1, fill: "none" },
        label: text({
          x: w / 2,
          y: headHeight / 2,
          fontSize: 12.5,
          fontWeight: 600,
          textWrap: { width: -20, height: -12, ellipsis: true },
        }),
        detail: {
          ...text({
            fontSize: 11,
            textAnchor: "start",
            textVerticalAnchor: "top",
            fontWeight: 400,
          }),
          x: 10,
          y: headHeight + 8,
          textWrap: { width: -20, height: -46, ellipsis: true },
        },
      };
    }
    case "milestone":
      return {
        body: { width: w, height: h, rx: 10, ry: 10, strokeWidth: 1 },
        tint: { width: w, height: h, rx: 10, ry: 10, strokeWidth: 0, fillOpacity: 0 },
        label: text({
          x: w / 2,
          y: h / 2 - 6,
          fontSize: 12.5,
          textWrap: { width: -24, height: -24, ellipsis: true },
        }),
      };
    case "stateNode":
      return {
        body: { width: w, height: h, rx: 10, ry: 10, strokeWidth: 1 },
        tint: { width: w, height: h, rx: 10, ry: 10, strokeWidth: 0, fillOpacity: 0 },
        accent: { x: 1.5, y: 6, width: 3.5, height: h - 12, rx: 1.75, strokeWidth: 0 },
        label: text({
          x: 18,
          y: h / 2,
          textAnchor: "start",
          fontSize: 12.5,
          textWrap: { width: -62, height: -16, ellipsis: true },
        }),
        badge: {
          ...text({
            fontSize: 10.5,
            textAnchor: "end",
            fontWeight: 400,
            fontFamily: GRAPH_MONO_STACK,
          }),
          x: w - 12,
          y: h / 2 + 1,
        },
      };
    case "statePseudo": {
      const r = Math.min(w, h) / 2;
      return {
        body: { cx: r, cy: r, r, strokeWidth: 1.5 },
        inner: { cx: r, cy: r, r: 0, strokeWidth: 0 },
      };
    }
    case "statePseudoFinal": {
      const r = Math.min(w, h) / 2;
      return {
        body: { cx: r, cy: r, r, strokeWidth: 1.5, fillOpacity: 0 },
        inner: { cx: r, cy: r, r: r - 4, strokeWidth: 0 },
      };
    }
    case "statePseudoChoice": {
      const hw = w / 2;
      return {
        body: { points: `${hw},0 ${w},${hw} ${hw},${h} 0,${hw}`, strokeWidth: 1.5 },
      };
    }
    case "dagNode":
      return {
        body: { width: w, height: h, rx: 6, ry: 6, strokeWidth: 1 },
        tint: { width: w, height: h, rx: 6, ry: 6, strokeWidth: 0, fillOpacity: 0 },
        icon: { d: "", transform: `translate(16, ${h / 2 - 8})`, strokeWidth: 1.5, fill: "none" },
        label: {
          ...text({ fontSize: 12.5, textAnchor: "start" }),
          x: 36,
          y: h / 2 + 1,
        },
        status: {
          d: "",
          transform: `translate(${w - 27}, ${h / 2 - 7})`,
          strokeWidth: 1.5,
          fill: "none",
        },
        statusDot: { cx: w - 20, cy: h / 2, r: 3.6, strokeWidth: 0, visibility: "hidden" },
      };
    case "dpNode":
      return {
        body: { width: w, height: h, rx: 8, ry: 8, strokeWidth: 1 },
        tint: { width: w, height: h, rx: 8, ry: 8, strokeWidth: 0, fillOpacity: 0 },
        tile: { x: 10, y: 10, width: 28, height: 28, rx: 7, ry: 7, strokeWidth: 0 },
        icon: { d: "", transform: "translate(16, 16)", strokeWidth: 1.5, fill: "none" },
        label: { ...text({ fontSize: 12.5, textAnchor: "start" }), x: 46, y: h / 2 - 6 },
        sublabel: {
          ...text({ fontSize: 10.5, textAnchor: "start", fontWeight: 400 }),
          x: 46,
          y: h / 2 + 11,
        },
        status: {
          d: "",
          transform: `translate(${w - 30}, ${h / 2 - 7})`,
          strokeWidth: 1.5,
          fill: "none",
        },
        statusDot: { cx: w - 23, cy: h / 2, r: 3.6, strokeWidth: 0, visibility: "hidden" },
      };
    case "orgNode":
      return {
        body: { width: w, height: h, rx: 10, ry: 10, strokeWidth: 1 },
        tint: { width: w, height: h, rx: 10, ry: 10, strokeWidth: 0, fillOpacity: 0 },
        avatar: { x: 10, y: 10, width: 36, height: 36, rx: 10, ry: 10, strokeWidth: 1 },
        initial: {
          ...text({ fontSize: 13, fontWeight: 600 }),
          x: 28,
          y: 28,
        },
        label: { ...text({ fontSize: 12.5, textAnchor: "start" }), x: 56, y: 22 },
        sublabel: {
          ...text({ fontSize: 10.5, textAnchor: "start", fontWeight: 400 }),
          x: 56,
          y: 39,
        },
        foldBg: { cx: w / 2, cy: h, r: 9.5, strokeWidth: 1 },
        foldText: {
          ...text({ fontSize: 9.5, fontFamily: GRAPH_MONO_STACK, fontWeight: 400 }),
          x: w / 2,
          y: h + 1,
        },
      };
    case "conceptNode": {
      const r = Math.min(w, h) / 2;
      return {
        body: { cx: r, cy: r, r, strokeWidth: 1.25 },
        tint: { cx: r, cy: r, r, strokeWidth: 0, fillOpacity: 0 },
        icon: {
          d: "",
          transform: `translate(${r - 8}, ${r - 8})`,
          strokeWidth: 1.4,
          fill: "none",
        },
        label: {
          ...text({ fontSize: 10.5, fontWeight: 400 }),
          x: r,
          y: h + 12,
        },
      };
    }
    case "archNode":
      return {
        body: { width: w, height: h, rx: 10, ry: 10, strokeWidth: 1 },
        tint: { width: w, height: h, rx: 10, ry: 10, strokeWidth: 0, fillOpacity: 0 },
        tile: { x: 9, y: 9, width: 34, height: 34, rx: 9, ry: 9, strokeWidth: 0 },
        icon: { d: "", transform: "translate(17, 17)", strokeWidth: 1.4, fill: "none" },
        label: { ...text({ fontSize: 12.5, textAnchor: "start" }), x: 53, y: 20 },
        sublabel: {
          ...text({ fontSize: 10.5, textAnchor: "start", fontWeight: 400 }),
          x: 53,
          y: 37,
        },
        tag: {
          ...text({
            fontSize: 9.5,
            textAnchor: "end",
            fontWeight: 400,
            fontFamily: GRAPH_MONO_STACK,
          }),
          x: w - 12,
          y: 15,
        },
      };
    case "mapRoot":
    case "mapBranch":
      return {
        body: {
          width: w,
          height: h,
          rx: shape === "mapRoot" ? 12 : 8,
          ry: shape === "mapRoot" ? 12 : 8,
          strokeWidth: shape === "mapRoot" ? 2 : 1,
        },
        tint: {
          width: w,
          height: h,
          rx: shape === "mapRoot" ? 12 : 8,
          ry: shape === "mapRoot" ? 12 : 8,
          strokeWidth: 0,
          fillOpacity: 0,
        },
        bar: { x: 0, y: 4, width: 3.5, height: h - 8, rx: 1.75, strokeWidth: 0 },
        label: text({
          x: w / 2 + 2,
          y: h / 2,
          fontSize: shape === "mapRoot" ? 13.5 : 12,
          fontWeight: shape === "mapRoot" ? 600 : 500,
          textWrap: { width: -22, height: -10, ellipsis: true },
        }),
      };
    case "mapLeaf":
      return {
        label: {
          ...text({ fontSize: 11.5, fontWeight: 400, textAnchor: "start" }),
          x: 2,
          y: h / 2 - 3,
        },
        baseline: { x: 0, y: h - 4, width: w, height: 2, rx: 1, strokeWidth: 0 },
      };
    default:
      return {};
  }
}

/**
 * 注册全部形态。由 GraphRenderer 在 `await import("@antv/x6")` 之后调用一次。
 */
export function registerGraphNodes(Graph: any): void {
  for (const [shape, [w, h]] of Object.entries(SHAPE_SIZES)) {
    const attrs = staticAttrs(shape, w, h);
    Graph.registerNode(
      `${SHAPE_REGISTRY_PREFIX}${shape}`,
      {
        inherit: "rect",
        width: w,
        height: h,
        markup: markupBody(shape, w, h, attrs),
        attrs,
        ports: {
          groups: {
            tb: {
              position: "top",
              attrs: { circle: { r: 3.4, strokeWidth: 1.2 } },
            },
            tbb: {
              position: "bottom",
              attrs: { circle: { r: 3.4, strokeWidth: 1.2 } },
            },
            lr: {
              position: "left",
              attrs: { circle: { r: 3.4, strokeWidth: 1.2 } },
            },
            lrr: {
              position: "right",
              attrs: { circle: { r: 3.4, strokeWidth: 1.2 } },
            },
          },
        },
      },
      true,
    );
  }
}

/** 形态是否为富节点（决定是否走 icon / 副行 / 徽标槽位）。 */
export function isRichShape(shape: string): boolean {
  return [
    "dagNode",
    "dpNode",
    "orgNode",
    "conceptNode",
    "archNode",
    "stateNode",
    "section",
  ].includes(shape);
}

/**
 * 把节点语义翻译成 attrs 覆盖值（颜色 + 文本 + 槽位）。
 * 配色逻辑只有这一处：body 描边 / tint 填充 / 文字色。
 */
export function nodeAttrs(
  node: GraphNode,
  shape: string,
  theme: GraphTheme,
  themeName: "dark" | "light",
  tone: GraphTone,
  extras: {
    iconPath?: string;
    bundle?: string;
    sublabel?: string;
    categoryColor?: string;
  } = {},
): Record<string, unknown> {
  const tinted = isTinted(tone);
  const stroke = extras.categoryColor ?? (tinted ? toneColor(tone, themeName) : theme.borderStrong);
  const attrs: Record<string, unknown> = {
    body: { fill: theme.surface, stroke, strokeWidth: 1 },
    tint: {
      fill: tinted ? toneColor(tone, themeName) : "transparent",
      fillOpacity: tinted ? 0.08 : 0,
    },
    label: { fill: theme.text },
  };

  if (shape === "cylinder") {
    attrs.cap = { fill: theme.surface, stroke };
  }
  if (shape === "section") {
    attrs.divider = { stroke: theme.borderStrong };
    attrs.detail = { fill: theme.textSecondary };
  }
  if (shape === "stateNode") {
    attrs.accent = { fill: toneColor(tone, themeName) };
    attrs.badge = { fill: theme.textMuted };
  }
  if (shape === "dagNode" || shape === "dpNode") {
    attrs.icon = { stroke: theme.textSecondary };
    attrs.tile = { fill: theme.surface2 };
    if (shape === "dpNode") attrs.sublabel = { fill: theme.textMuted };
  }
  if (shape === "orgNode") {
    attrs.avatar = { fill: theme.surface2, stroke: theme.borderStrong };
    attrs.initial = { fill: theme.textSecondary };
    attrs.sublabel = { fill: theme.textMuted };
    attrs.foldBg = { fill: theme.surface2, stroke: theme.borderStrong };
    attrs.foldText = { fill: theme.textSecondary };
  }
  if (shape === "conceptNode") {
    attrs.icon = { stroke: theme.textSecondary };
    attrs.label = { fill: theme.textSecondary };
  }
  if (shape === "archNode") {
    attrs.tile = { fill: theme.surface2 };
    attrs.icon = { stroke: theme.textSecondary };
    attrs.sublabel = { fill: theme.textMuted };
    attrs.tag = { fill: theme.textMuted };
  }
  if (shape === "mapRoot" || shape === "mapBranch") {
    const bar = extras.categoryColor ?? theme.borderStrong;
    attrs.bar = { fill: bar };
  }
  if (shape === "mapLeaf") {
    attrs.baseline = { fill: extras.categoryColor ?? theme.borderStrong };
    attrs.label = { fill: theme.textSecondary };
  }
  if (shape === "statePseudo" || shape === "statePseudoFinal") {
    attrs.body = { fill: theme.text, stroke: theme.text, strokeWidth: 1.5 };
    if (shape === "statePseudoFinal") {
      attrs.body = { fill: "transparent", stroke: theme.text, strokeWidth: 1.5 };
      attrs.inner = { fill: theme.text };
    }
  }
  if (shape === "statePseudoChoice") {
    attrs.body = { fill: "transparent", stroke: theme.text, strokeWidth: 1.5 };
  }
  if (shape === "diamond") {
    attrs.body = { fill: theme.surface, stroke };
  }
  if (extras.iconPath) {
    attrs.icon = { ...(attrs.icon as object), d: extras.iconPath };
  }
  return attrs;
}

export type { GraphTheme };
