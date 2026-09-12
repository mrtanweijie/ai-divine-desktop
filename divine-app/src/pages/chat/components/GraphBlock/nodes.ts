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

/**
 * 分组框（cluster / lane / boundary）专用形态名。
 *
 * **不要用内置 `rect` 画分组框**：内置 rect 的默认 attrs 里 `label` 带
 * `refX: 0.5, refY: 0.5`（居中语义），我们的标题只覆盖 x/y，refX/refY 会残留，
 * 定位变成"半宽 + x" —— 标题被推到框的右下角。改用自有 `title` 槽位即可避开。
 */
export const GROUP_FRAME_SHAPE = "gb-frame";

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
        { tagName: "text", selector: "title" },
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
        { tagName: "text", selector: "title" },
      ];
    }
    case "cylinder":
      return [
        { tagName: "path", selector: "body" },
        { tagName: "ellipse", selector: "cap" },
        { tagName: "text", selector: "title" },
      ];
    case "section":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "path", selector: "divider" },
        { tagName: "text", selector: "title" },
        { tagName: "text", selector: "detail" },
      ];
    case "dagNode":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "path", selector: "icon" },
        { tagName: "text", selector: "title" },
        { tagName: "path", selector: "status" },
        { tagName: "circle", selector: "statusDot" },
      ];
    case "dpNode":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "rect", selector: "tile" },
        { tagName: "path", selector: "icon" },
        { tagName: "text", selector: "title" },
        { tagName: "text", selector: "sublabel" },
        { tagName: "path", selector: "status" },
        { tagName: "circle", selector: "statusDot" },
      ];
    case "stateNode":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "rect", selector: "accent" },
        { tagName: "text", selector: "title" },
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
        { tagName: "text", selector: "title" },
        { tagName: "text", selector: "sublabel" },
        { tagName: "circle", selector: "foldBg" },
        { tagName: "text", selector: "foldText" },
      ];
    case "conceptNode":
      return [
        { tagName: "circle", selector: "body" },
        { tagName: "circle", selector: "tint" },
        { tagName: "path", selector: "icon" },
        { tagName: "text", selector: "title" },
      ];
    case "archNode":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "rect", selector: "tile" },
        { tagName: "path", selector: "icon" },
        { tagName: "text", selector: "title" },
        { tagName: "text", selector: "sublabel" },
        { tagName: "text", selector: "tag" },
      ];
    case "mapRoot":
    case "mapBranch":
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "rect", selector: "bar" },
        { tagName: "text", selector: "title" },
      ];
    case "mapLeaf":
      return [
        { tagName: "text", selector: "title" },
        { tagName: "rect", selector: "baseline" },
      ];
    default:
      return [
        { tagName: "rect", selector: "body" },
        { tagName: "rect", selector: "tint" },
        { tagName: "text", selector: "title" },
      ];
  }
}

/** markup 里的 text selector 列表（按形态缓存，避免重复构建）。 */
const textSelectorCache = new Map<string, string[]>();

function textSelectorsOf(shape: string, w: number, h: number): string[] {
  const cached = textSelectorCache.get(shape);
  if (cached) return cached;
  const list = markupBody(shape, w, h, {})
    .filter((item) => item.tagName === "text")
    .map((item) => item.selector);
  textSelectorCache.set(shape, list);
  return list;
}

/**
 * 把 text 的坐标从「相对节点左上角」换算成「相对节点中心」。
 *
 * **必须做这一步**：X6 对带 `textAnchor` / `textVerticalAnchor` 的 `<text>`
 * 会额外加 `transform="matrix(1,0,0,1, w/2, h/2)"`（把原点挪到节点中心），
 * 而 `rect` / `path` / `circle` 这些元素仍以左上角为原点。
 * 不换算的话，文字整体右下偏移半个身位——表现就是"文字飘在框外"。
 *
 * 本文件的形态定义一律用「相对左上角」书写（和其他元素同一套坐标，好读），
 * 出口处统一换算。
 */
export function shiftTextAnchors<T extends Record<string, unknown>>(
  attrs: T,
  shape: string,
  w: number,
  h: number,
): T {
  const out: Record<string, unknown> = { ...attrs };
  const round = (value: number) => Math.round(value * 100) / 100;
  for (const selector of textSelectorsOf(shape, w, h)) {
    const value = out[selector];
    if (!value || typeof value !== "object") continue;
    const next: Record<string, unknown> = { ...(value as Record<string, unknown>) };
    if (typeof next.x === "number") next.x = round(next.x - w / 2);
    if (typeof next.y === "number") next.y = round(next.y - h / 2);
    out[selector] = next;
  }
  return out as T;
}

/**
 * 形态的静态 attrs（尺寸相关的几何一律在这里算死，运行时只改颜色）。
 *
 * 导出给 :func:`nodeAttrs` 做**显式合并**：X6 对 addNode 传入的 attrs 与注册
 * 默认值的合并是逐 selector 深合并，但依赖隐式语义太脆（曾出现几何 attrs
 * 被覆盖成默认值、节点画成小方块）。这里改为先铺几何、再叠颜色，行为确定。
 */
export function shapeStaticAttrs(shape: string, w: number, h: number) {
  return staticAttrs(shape, w, h);
}

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
        title: text({
          x: w / 2,
          y: h / 2,
          textWrap: { width: -32, height: -16, ellipsis: true },
        }),
      };
    case "rounded":
      return {
        body: { width: w, height: h, rx: 8, ry: 8, strokeWidth: 1 },
        tint: { width: w, height: h, rx: 8, ry: 8, strokeWidth: 0, fillOpacity: 0 },
        title: text({
          x: w / 2,
          y: h / 2,
          textWrap: { width: -32, height: -16, ellipsis: true },
        }),
      };
    case "diamond":
      return {
        body: { strokeWidth: 1, strokeLinejoin: "round" },
        title: text({
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
        title: text({
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
        title: text({
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
        title: text({
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
        title: text({
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
        title: {
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
        title: { ...text({ fontSize: 12.5, textAnchor: "start" }), x: 46, y: h / 2 - 6 },
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
        title: { ...text({ fontSize: 12.5, textAnchor: "start" }), x: 56, y: 22 },
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
        title: {
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
        title: { ...text({ fontSize: 12.5, textAnchor: "start" }), x: 53, y: 20 },
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
        title: text({
          x: w / 2 + 2,
          y: h / 2,
          fontSize: shape === "mapRoot" ? 13.5 : 12,
          fontWeight: shape === "mapRoot" ? 600 : 500,
          textWrap: { width: -22, height: -10, ellipsis: true },
        }),
      };
    case "mapLeaf":
      return {
        title: {
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
  // 分组框：只有 body + title 两个槽位，标题语义明确（左上角内缩 10/16）
  Graph.registerNode(
    GROUP_FRAME_SHAPE,
    {
      inherit: "rect",
      markup: [
        { tagName: "rect", selector: "body" },
        { tagName: "text", selector: "title" },
      ],
      attrs: {
        body: { fill: "transparent", stroke: "none", strokeWidth: 1, rx: 12, ry: 12 },
        title: {
          fill: "#000",
          fontSize: 10.5,
          fontFamily: GRAPH_MONO_STACK,
          textAnchor: "start",
          textVerticalAnchor: "middle",
          x: 10,
          y: 16,
        },
      },
    },
    true,
  );

  for (const [shape, [w, h]] of Object.entries(SHAPE_SIZES)) {
    const attrs = staticAttrs(shape, w, h);
    // markupBody 会往 attrs 里塞几何（如 diamond 的 points），先构建再换算 text
    const markup = markupBody(shape, w, h, attrs);
    Graph.registerNode(
      `${SHAPE_REGISTRY_PREFIX}${shape}`,
      {
        inherit: "rect",
        width: w,
        height: h,
        markup,
        attrs: shiftTextAnchors(attrs, shape, w, h),
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
  // 先铺该形态的几何 attrs（宽高 / 坐标 / 字号），再逐 selector 覆盖颜色——
  // 顺序反过来会把 width/height 覆盖掉，节点会被画成默认小矩形。
  const size = SHAPE_SIZES[shape] ?? [136, 46];
  const attrs: Record<string, unknown> = { ...shapeStaticAttrs(shape, size[0], size[1]) };
  attrs.body = { ...(attrs.body as object), fill: theme.surface, stroke, strokeWidth: 1 };
  attrs.tint = {
    ...(attrs.tint as object),
    ...{
      ...(attrs.tint as object),
      fill: tinted ? toneColor(tone, themeName) : "transparent",
      fillOpacity: tinted ? 0.08 : 0,
    },
  };
  attrs.title = { ...(attrs.title as object), fill: theme.text };

  if (shape === "cylinder") {
    attrs.cap = { ...(attrs.cap as object), ...{ fill: theme.surface, stroke } };
  }
  if (shape === "section") {
    attrs.divider = { ...(attrs.divider as object), ...{ stroke: theme.borderStrong } };
    attrs.detail = { ...(attrs.detail as object), ...{ fill: theme.textSecondary } };
  }
  if (shape === "stateNode") {
    attrs.accent = { ...(attrs.accent as object), ...{ fill: toneColor(tone, themeName) } };
    attrs.badge = { ...(attrs.badge as object), ...{ fill: theme.textMuted } };
  }
  if (shape === "dagNode" || shape === "dpNode") {
    attrs.icon = { ...(attrs.icon as object), ...{ stroke: theme.textSecondary } };
    attrs.tile = { ...(attrs.tile as object), ...{ fill: theme.surface2 } };
    if (shape === "dpNode")
      attrs.sublabel = { ...(attrs.sublabel as object), ...{ fill: theme.textMuted } };
  }
  if (shape === "orgNode") {
    attrs.avatar = {
      ...(attrs.avatar as object),
      ...{ fill: theme.surface2, stroke: theme.borderStrong },
    };
    attrs.initial = { ...(attrs.initial as object), ...{ fill: theme.textSecondary } };
    attrs.sublabel = { ...(attrs.sublabel as object), ...{ fill: theme.textMuted } };
    attrs.foldBg = {
      ...(attrs.foldBg as object),
      ...{ fill: theme.surface2, stroke: theme.borderStrong },
    };
    attrs.foldText = { ...(attrs.foldText as object), ...{ fill: theme.textSecondary } };
  }
  if (shape === "conceptNode") {
    attrs.icon = { ...(attrs.icon as object), ...{ stroke: theme.textSecondary } };
    attrs.title = { ...(attrs.title as object), ...{ fill: theme.textSecondary } };
  }
  if (shape === "archNode") {
    attrs.tile = { ...(attrs.tile as object), ...{ fill: theme.surface2 } };
    attrs.icon = { ...(attrs.icon as object), ...{ stroke: theme.textSecondary } };
    attrs.sublabel = { ...(attrs.sublabel as object), ...{ fill: theme.textMuted } };
    attrs.tag = { ...(attrs.tag as object), ...{ fill: theme.textMuted } };
  }
  if (shape === "mapRoot" || shape === "mapBranch") {
    const bar = extras.categoryColor ?? theme.borderStrong;
    attrs.bar = { ...(attrs.bar as object), ...{ fill: bar } };
  }
  if (shape === "mapLeaf") {
    attrs.baseline = {
      ...(attrs.baseline as object),
      ...{ fill: extras.categoryColor ?? theme.borderStrong },
    };
    attrs.title = { ...(attrs.title as object), ...{ fill: theme.textSecondary } };
  }
  if (shape === "statePseudo" || shape === "statePseudoFinal") {
    attrs.body = {
      ...(attrs.body as object),
      ...{ fill: theme.text, stroke: theme.text, strokeWidth: 1.5 },
    };
    if (shape === "statePseudoFinal") {
      attrs.body = {
        ...(attrs.body as object),
        ...{ fill: "transparent", stroke: theme.text, strokeWidth: 1.5 },
      };
      attrs.inner = { ...(attrs.inner as object), ...{ fill: theme.text } };
    }
  }
  if (shape === "statePseudoChoice") {
    attrs.body = {
      ...(attrs.body as object),
      ...{ fill: "transparent", stroke: theme.text, strokeWidth: 1.5 },
    };
  }
  if (shape === "diamond") {
    attrs.body = { ...(attrs.body as object), ...{ fill: theme.surface, stroke } };
  }
  if (extras.iconPath) {
    attrs.icon = { ...(attrs.icon as object), d: extras.iconPath };
  }
  // 出口统一换算 text 坐标（左上角 → 中心），见 shiftTextAnchors 说明
  return shiftTextAnchors(attrs, shape, size[0], size[1]);
}

export type { GraphTheme };
