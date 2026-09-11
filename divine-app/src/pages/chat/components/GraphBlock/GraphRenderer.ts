/**
 * GraphRenderer —— 场景无关的渲染器：`IR × Preset → X6 图`。
 *
 * 职责边界（004 架构图）：
 * - 只认 IR + Preset，**不认具体场景**——15 个场景共用这一条路径；
 * - 布局只跑一次（完整 IR 到达后）；
 * - 入场动画是**回放式**：完整 IR 已在手，由前端按序展开播放（004 决策 13）；
 * - 导出走 `graph.toSVG()/toPNG()`，因此节点/边必须是纯 SVG markup。
 *
 * 入场动效走 CSS 类 + `animation-delay`（而非 X6 的 `animate` API）：
 * X6 动画 API 的真实形状仍在 P0 清单第 1 条待实测，CSS 路径不依赖它、
 * 可被 `prefers-reduced-motion` 一键关闭，且天然是"终态优先"的降级形态。
 */

import { type GraphIR, type GraphNode, nodeTone } from "./GraphIR";
import { iconPath, STATUS_MARKS, ARCH_ICONS, STATUS_TONE } from "./icons";
import { computeLayout } from "./layouts";
import { registerGraphNodes, SHAPE_SIZES, nodeAttrs, truncateToWidth } from "./nodes";
import { type GraphTheme, graphTheme, type GraphThemeName } from "./graphTheme";
import { assignColorIndexes, branchColor } from "./graphTones";
import { baseLineAttrs, ensureFlowKeyframes, flowAttrs, labelParts } from "./edges";
import { type ScenarioPreset, shapeForNode } from "./presets";
import { AnimationManager } from "./AnimationManager";
import { RenderScheduler } from "./RenderScheduler";

/* eslint-disable @typescript-eslint/no-explicit-any -- 动态 import 的 X6 命名空间 */

const PADDING = 28;

export interface GraphRendererOptions {
  container: HTMLElement;
  ir: GraphIR;
  preset: ScenarioPreset;
  theme: GraphThemeName;
  /** 新消息播放回放式入场；历史消息直渲染终态（零动画） */
  animate: boolean;
  onSelectNode?: (node: GraphNode | null) => void;
  onDemoStep?: (nodeId: string) => void;
}

export interface GraphRendererApi {
  replay(): void;
  setFlow(enabled: boolean): void;
  playDemo(): void;
  stopDemo(): void;
  exportSVG(): Promise<string>;
  exportPNG(pixelRatio?: number): Promise<string>;
  dispose(): void;
}

const DEMO_STEP_MS = 600;

/** 节点的实际尺寸（含 concept 圆按度定尺寸的近似：按 label 长度微调）。 */
function nodeSize(node: GraphNode, shape: string): { w: number; h: number } {
  const [w, h] = SHAPE_SIZES[shape] ?? [136, 46];
  return { w, h };
}

/** 富节点的文本槽位内容。 */
function richText(node: GraphNode, shape: string): Record<string, string> {
  switch (shape) {
    case "dagNode":
      return { label: truncateToWidth(node.label ?? "", 118, 12.5) };
    case "dpNode":
      return {
        label: truncateToWidth(node.label ?? "", 132, 12.5),
        sublabel: truncateToWidth(node.sublabel ?? "", 132, 10.5),
      };
    case "archNode":
      return {
        label: truncateToWidth(node.label ?? "", 100, 12.5),
        sublabel: truncateToWidth(node.sublabel ?? "", 100, 10.5),
        tag: node.tag ?? "",
      };
    case "orgNode":
      return {
        initial: (node.label ?? "?").trim().charAt(0),
        label: truncateToWidth(node.label ?? "", 104, 12.5),
        sublabel: truncateToWidth(node.role_desc ?? "", 104, 10.5),
        foldText: typeof node.count === "number" ? String(node.count) : "",
      };
    case "conceptNode":
      return { label: truncateToWidth(node.label ?? "", 96, 10.5) };
    case "stateNode":
      return {
        label: truncateToWidth(node.label ?? "", 84, 12.5),
        badge: node.badge ?? "",
      };
    case "section":
      return {
        label: truncateToWidth(node.label ?? "", 156, 12.5),
        detail: truncateToWidth(node.note ?? "", 156, 11),
      };
    default:
      return { label: node.label ?? "" };
  }
}

function iconForNode(node: GraphNode, shape: string): string {
  if (shape === "archNode") return ARCH_ICONS[node.type ?? "backend"] ?? ARCH_ICONS.backend;
  if (shape === "conceptNode") return iconPath("concept", node.type ?? "module");
  if (shape === "dpNode") return iconPath("flow", node.icon ?? "");
  if (shape === "dagNode") return iconPath("task", node.icon ?? "");
  return "";
}

export async function createGraphRenderer(
  options: GraphRendererOptions,
): Promise<GraphRendererApi> {
  const { container, ir, preset, theme: themeName, animate, onSelectNode, onDemoStep } = options;
  const theme: GraphTheme = graphTheme(themeName);

  ensureFlowKeyframes();

  const [x6, layoutNs] = await Promise.all([import("@antv/x6"), import("@antv/layout")]);
  const { Graph, Edge } = x6 as any;
  registerGraphNodes(Graph);

  // ── 双层边：底线 + 流动层（Edge.config 全局一次）
  Edge.config({
    markup: [
      { tagName: "path", selector: "line", attrs: { fill: "none" } },
      { tagName: "path", selector: "flow", attrs: { fill: "none" } },
      { tagName: "text", selector: "labelText", attrs: { fill: "none" } },
    ],
  });

  const scheduler = new RenderScheduler(80);
  const animations = new AnimationManager();

  const graph = new Graph({
    container,
    background: { color: "transparent" },
    grid: false,
    panning: preset.level === "L0" ? false : { enabled: true, eventTypes: ["leftMouseDown"] },
    mousewheel: { enabled: true, modifiers: ["ctrl", "meta"], minScale: 0.4, maxScale: 2 },
    interacting: { nodeMovable: false, edgeMovable: false, arrowheadMovable: false },
    connecting: {
      router: { name: preset.edges.router },
      connector:
        preset.edges.connector === "rounded"
          ? { name: "rounded", args: { radius: 8 } }
          : { name: "smooth" },
    },
    async: true,
  });

  // 类别色 / 分支色由前端按首次出现顺序分配（IR 里没有色）
  const nodeShapes = new Map<string, string>();
  for (const node of ir.nodes) nodeShapes.set(node.id, shapeForNode(preset, node));
  const categoryIndex = assignColorIndexes(
    ir.nodes.map((node) => node.category).filter((value): value is string => !!value),
  );
  const colorOf = (node: GraphNode): string | undefined => {
    if (node.category && categoryIndex.has(node.category)) {
      return branchColor(categoryIndex.get(node.category) as number, themeName);
    }
    return undefined;
  };

  // ── 布局（一次）
  const layout = computeLayout(layoutNs as any, ir, preset, (node) =>
    nodeSize(node, nodeShapes.get(node.id) as string),
  );

  const viewBox = () => {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const node of ir.nodes) {
      const point = layout.positions[node.id];
      if (!point) continue;
      const size = nodeSize(node, nodeShapes.get(node.id) as string);
      minX = Math.min(minX, point.x - size.w / 2);
      maxX = Math.max(maxX, point.x + size.w / 2);
      minY = Math.min(minY, point.y - size.h / 2);
      maxY = Math.max(maxY, point.y + size.h / 2);
    }
    if (!Number.isFinite(minX)) return null;
    if (layout.extras?.lifelineBottom) maxY = Math.max(maxY, layout.extras.lifelineBottom);
    return { minX, minY, maxX, maxY };
  };

  const box = viewBox();
  const offset = box
    ? { x: PADDING - box.minX, y: PADDING - box.minY }
    : { x: PADDING, y: PADDING };

  // ── 容器组（cluster / lane / boundary）：垫底、不可交互
  if (preset.groups) {
    const groups = [...(ir.groups ?? [])];
    // 边界按成员数降序绘制 → 大框在底层，小框叠上即嵌套视觉（020 §5.7）
    if (preset.groups === "boundary") {
      groups.sort((a, b) => b.members.length - a.members.length);
    }
    groups.forEach((group, index) => {
      const points = group.members
        .map((id) => layout.positions[id])
        .filter((point): point is { x: number; y: number } => !!point);
      if (!points.length) return;
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const id of group.members) {
        const point = layout.positions[id];
        if (!point) continue;
        const size = nodeSize(
          ir.nodes.find((node) => node.id === id) as GraphNode,
          nodeShapes.get(id) as string,
        );
        minX = Math.min(minX, point.x - size.w / 2);
        maxX = Math.max(maxX, point.x + size.w / 2);
        minY = Math.min(minY, point.y - size.h / 2);
        maxY = Math.max(maxY, point.y + size.h / 2);
      }
      const isBoundary = ["region", "vpc", "security-group"].includes(group.type);
      const isLane = group.type === "lane";
      const laneHeight = preset.layout.laneHeight ?? 124;
      const pad = isBoundary ? (group.type === "region" ? 22 : 12) : 16;
      const x = offset.x + (isLane ? 0 : minX - pad);
      const y = offset.y + (isLane ? index * laneHeight + 5 : minY - pad);
      const width = isLane
        ? box
          ? box.maxX - box.minX + PADDING * 2
          : 480
        : maxX - minX + pad * 2;
      const height = isLane ? laneHeight - 10 : maxY - minY + pad * 2;
      graph.addNode({
        id: `__group_${group.id}`,
        shape: "rect",
        x,
        y,
        width,
        height,
        zIndex: -1,
        interactive: false,
        attrs: {
          body: {
            fill: isLane ? theme.laneFill : theme.clusterFill,
            stroke: theme.clusterStroke,
            strokeWidth: isBoundary && group.type !== "region" ? 1.2 : 1,
            strokeDasharray: preset.frameLanes && isLane ? "5 4" : "4 4",
            rx: isBoundary ? (group.type === "region" ? 14 : 10) : 12,
            ry: isBoundary ? (group.type === "region" ? 14 : 10) : 12,
          },
          label: {
            text: group.label ?? "",
            refX: 0.02,
            refY: 0,
            textAnchor: "start",
            textVerticalAnchor: "bottom",
            fill: theme.textSecondary,
            fontSize: 10.5,
            fontFamily:
              themeName === "dark" ? "ui-monospace, monospace" : "ui-monospace, monospace",
          },
        },
      });
    });
  }

  // ── 节点
  for (const node of ir.nodes) {
    const shape = nodeShapes.get(node.id) as string;
    const point = layout.positions[node.id] ?? { x: 0, y: 0 };
    const size = nodeSize(node, shape);
    const tone = nodeTone(node);
    const text = richText(node, shape);
    const iconD = iconForNode(node, shape);
    const attrs = nodeAttrs(node, shape, theme, themeName, tone, {
      iconPath: iconD,
      categoryColor: colorOf(node),
    });
    for (const [selector, value] of Object.entries(text)) {
      const existing = (attrs[selector] as Record<string, unknown>) ?? {};
      attrs[selector] = { ...existing, text: value };
    }
    if (shape === "dagNode" || shape === "dpNode") {
      const state = node.state ?? "pending";
      attrs.status = {
        ...(attrs.status as object),
        d: STATUS_MARKS[state] ?? "",
        stroke: themeName === "dark" ? "#8A94A6" : "#7A8494",
      };
      if (state === "running") {
        // running：实心点 + 1.5s 脉冲（020 §5.5 状态徽标 4 态）
        attrs.statusDot = {
          ...(attrs.statusDot as object),
          visibility: "visible",
          fill: themeName === "dark" ? "#61A7D0" : "#036EAD",
        };
      } else {
        attrs.statusDot = { ...(attrs.statusDot as object), visibility: "hidden" };
        const markTone = STATUS_TONE[state] ?? "neutral";
        attrs.status = {
          ...(attrs.status as object),
          stroke:
            markTone === "success"
              ? themeName === "dark"
                ? "#3FB98A"
                : "#2F9E6E"
              : markTone === "error"
                ? themeName === "dark"
                  ? "#E07A82"
                  : "#C9525B"
                : themeName === "dark"
                  ? "#8A94A6"
                  : "#7A8494",
          strokeDasharray: state === "pending" ? "2 2" : undefined,
        };
      }
    }
    if (shape === "orgNode" && typeof node.count !== "number") {
      attrs.foldBg = { ...(attrs.foldBg as object), visibility: "hidden" };
      attrs.foldText = { ...(attrs.foldText as object), text: "" };
    }

    graph.addNode({
      id: node.id,
      shape: `graph-${shape}`,
      x: point.x + offset.x,
      y: point.y + offset.y,
      width: size.w,
      height: size.h,
      zIndex: 10,
      attrs,
      data: { gbNode: node },
    });
  }

  // ── 边（底线 + 流动层；自环与 UML 标签）
  for (const edge of ir.edges) {
    const line = baseLineAttrs(edge, preset.edges, themeName, theme);
    const flow = flowAttrs(edge, themeName);
    const parts = labelParts(edge.label);
    graph.addEdge({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      router: { name: preset.edges.router },
      connector:
        preset.edges.connector === "rounded"
          ? { name: "rounded", args: { radius: 8 } }
          : { name: "smooth" },
      defaultLabel: parts
        ? {
            position: { distance: 0.5 },
            attrs: {
              label: {
                text: parts.guard ? `${parts.event} ` : parts.event,
                fill: theme.textSecondary,
                fontSize: 11,
                fontFamily: "system-ui, sans-serif",
              },
              body: {
                fill: theme.labelBg,
                stroke: theme.clusterStroke,
                strokeWidth: 1,
                rx: 4,
                ry: 4,
              },
            },
          }
        : undefined,
      attrs: {
        line,
        flow: flow ?? { stroke: "transparent", strokeWidth: 0 },
        labelText: { text: "", fill: "transparent" },
      },
      data: { gbEdge: edge },
    });
  }

  graph.centerContent();

  // ── 回放式入场：按 nodes → edges 顺序展开，CSS 类驱动
  const nodeElements = () =>
    Array.from(container.querySelectorAll<SVGGElement>(".x6-node[data-cell-id]"));
  const edgeElements = () =>
    Array.from(container.querySelectorAll<SVGGElement>(".x6-edge[data-cell-id]"));

  const replay = () => {
    if (!animate) return;
    container.classList.remove("gb-entering");
    // 强制回流，保证重复重播时动画重新开始
    void container.offsetWidth;
    container.classList.add("gb-entering");
    container.style.setProperty("--gb-stagger", `${preset.motion.stagger}ms`);
    nodeElements().forEach((element, index) => {
      element.style.animationDelay = `${index * preset.motion.stagger}ms`;
    });
    const nodeSpan = ir.nodes.length * preset.motion.stagger;
    edgeElements().forEach((element, index) => {
      element.style.animationDelay = `${nodeSpan + index * 40}ms`;
    });
    animations.track("entrance", nodeSpan + ir.edges.length * 40 + 480);
  };

  // ── 流动开关（会话内同时开启流动的块 ≤ 3，见 020 §7 硬约束 1b）
  let flowEnabled = false;
  const setFlow = (enabled: boolean) => {
    flowEnabled = enabled;
    container.classList.toggle("gb-flow", enabled);
    if (enabled) {
      animations.claimFlowSlot(() => setFlow(false));
      scheduler.schedule(() => {
        edgeElements().forEach((element, index) => {
          const path = element.querySelectorAll("path")[1];
          if (!path) return;
          const edge = ir.edges[index];
          const speed = edge?.flow?.speed ?? 1;
          (path as SVGPathElement).style.animation = `graph-dash ${1.1 / speed}s linear infinite`;
        });
      });
    } else {
      animations.releaseFlowSlot();
      edgeElements().forEach((element) => {
        const path = element.querySelectorAll("path")[1] as SVGPathElement | undefined;
        if (path) path.style.animation = "";
      });
    }
  };

  // ── hover 关联高亮：邻接关系来自 IR（不靠几何推断）
  const adjacency = new Map<string, Set<string>>();
  for (const node of ir.nodes) adjacency.set(node.id, new Set([node.id]));
  for (const edge of ir.edges) {
    adjacency.get(edge.source)?.add(edge.target);
    adjacency.get(edge.target)?.add(edge.source);
  }
  const clearFocus = () => {
    container.classList.remove("gb-focus");
    container.querySelectorAll(".gb-hl").forEach((element) => element.classList.remove("gb-hl"));
  };
  const onNodeEnter = (nodeId: string) => {
    const related = adjacency.get(nodeId);
    if (!related) return;
    container.classList.add("gb-focus");
    for (const id of related) {
      container.querySelector(`.x6-node[data-cell-id="${id}"]`)?.classList.add("gb-hl");
    }
    for (const edge of ir.edges) {
      if (edge.source === nodeId || edge.target === nodeId) {
        container.querySelector(`.x6-edge[data-cell-id="${edge.id}"]`)?.classList.add("gb-hl");
      }
    }
  };

  graph.on("node:mouseenter", ({ node }: any) => {
    animations.pause("hover");
    onNodeEnter(node.id);
  });
  graph.on("node:mouseleave", () => {
    animations.resume("hover");
    clearFocus();
  });
  graph.on("node:click", ({ node }: any) => {
    const data = node.getData() as { gbNode?: GraphNode } | undefined;
    onSelectNode?.(data?.gbNode ?? null);
  });
  graph.on("blank:click", () => onSelectNode?.(null));

  // ── demoPath 播放
  let demoTimer: number | null = null;
  const stopDemo = () => {
    if (demoTimer !== null) window.clearTimeout(demoTimer);
    demoTimer = null;
    container.classList.remove("gb-demo");
    container
      .querySelectorAll(".gb-active")
      .forEach((element) => element.classList.remove("gb-active"));
  };
  const playDemo = () => {
    stopDemo();
    const path = ir.demoPath ?? [];
    if (!path.length) return;
    container.classList.add("gb-demo");
    path.forEach((nodeId, index) => {
      demoTimer = window.setTimeout(() => {
        const element = container.querySelector(`.x6-node[data-cell-id="${nodeId}"]`);
        element?.classList.add("gb-active");
        onDemoStep?.(nodeId);
        if (index === path.length - 1) demoTimer = null;
      }, index * DEMO_STEP_MS);
    });
  };

  // ── 导出（前端主导，004 决策 14）
  const exportSVG = async (): Promise<string> => {
    const wasFlow = flowEnabled;
    if (wasFlow) setFlow(false);
    try {
      const result = graph.toSVG();
      const svg = typeof result === "string" ? result : await result;
      return svg as string;
    } finally {
      if (wasFlow) setFlow(true);
    }
  };
  const exportPNG = (pixelRatio = 2): Promise<string> =>
    new Promise((resolve, reject) => {
      try {
        graph.toPNG((dataUri: string) => resolve(dataUri), {
          backgroundColor: theme.surface,
          padding: 16,
          pixelRatio,
        });
      } catch (error) {
        reject(error);
      }
    });

  const dispose = () => {
    stopDemo();
    animations.releaseFlowSlot();
    animations.disposeAll();
    scheduler.dispose();
    graph.dispose();
  };

  // 历史消息：直渲染终态（零动画、不自动开流动）
  if (animate) replay();
  else container.classList.add("gb-static");

  return { replay, setFlow, playDemo, stopDemo, exportSVG, exportPNG, dispose };
}
