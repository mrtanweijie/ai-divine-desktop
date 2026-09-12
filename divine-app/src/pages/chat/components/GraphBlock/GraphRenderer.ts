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
import {
  GROUP_FRAME_SHAPE,
  registerGraphNodes,
  SHAPE_SIZES,
  nodeAttrs,
  truncateToWidth,
} from "./nodes";
import { type GraphTheme, GRAPH_MONO_STACK, graphTheme, type GraphThemeName } from "./graphTheme";
import { assignColorIndexes, branchColor } from "./graphTones";
import { baseLineAttrs, ensureFlowKeyframes, flowAttrs, labelParts } from "./edges";
import { type ScenarioPreset, shapeForNode } from "./presets";
import { AnimationManager } from "./AnimationManager";
import { RenderScheduler } from "./RenderScheduler";

/* eslint-disable @typescript-eslint/no-explicit-any -- 动态 import 的 X6 命名空间 */

const PADDING = 28;

/** 自适配缩放下限（12.5px 字的下限；更小就交给用户 Ctrl+滚轮放大）。 */
const MIN_FIT_SCALE = 0.4;

/**
 * 画布高度区间。下限保证即使是很扁的宽图，画布也有足够的可视高度
 * （不随宽度适配比一起被压扁）；上限避免单条消息把会话撑得过长。
 */
export const CANVAS_MIN_HEIGHT = 360;
export const CANVAS_MAX_HEIGHT = 900;

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
  /** 内容原始尺寸（未缩放，含内边距）。 */
  readonly contentSize: { width: number; height: number };
  /**
   * 画布尺寸：小图按内容高度撑开（1:1、不用滚动）；大图高度封顶到
   * MAX_CANVAS_HEIGHT，由 `zoomToFit` 双向适配把整幅图缩进可视区。
   */
  measure(): { width: number; height: number };
  /** 容器尺寸变化后重算画布尺寸与缩放。 */
  resize(): void;
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
      return { title: truncateToWidth(node.label ?? "", 118, 12.5) };
    case "dpNode":
      return {
        title: truncateToWidth(node.label ?? "", 132, 12.5),
        sublabel: truncateToWidth(node.sublabel ?? "", 132, 10.5),
      };
    case "archNode":
      return {
        title: truncateToWidth(node.label ?? "", 100, 12.5),
        sublabel: truncateToWidth(node.sublabel ?? "", 100, 10.5),
        tag: node.tag ?? "",
      };
    case "orgNode":
      return {
        initial: (node.label ?? "?").trim().charAt(0),
        title: truncateToWidth(node.label ?? "", 104, 12.5),
        sublabel: truncateToWidth(node.role_desc ?? "", 104, 10.5),
        foldText: typeof node.count === "number" ? String(node.count) : "",
      };
    case "conceptNode":
      return { title: truncateToWidth(node.label ?? "", 96, 10.5) };
    case "stateNode":
      return {
        title: truncateToWidth(node.label ?? "", 84, 12.5),
        badge: node.badge ?? "",
      };
    case "section":
      return {
        title: truncateToWidth(node.label ?? "", 156, 12.5),
        detail: truncateToWidth(node.note ?? "", 156, 11),
      };
    default:
      return { title: node.label ?? "" };
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
  // Export 是 `@antv/x6` 主入口导出的内置插件（export 不属于 graph 内核）。
  // **必须 use 它**：不挂载时 `graph.toSVG/toPNG` 虽然存在于原型上，但内部
  // `getPlugin('export')` 为 null，会静默什么都不做也不回调——导出拿到 undefined。
  const { Graph, Edge, Export } = x6 as any;
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

  // 独立挂载点：React StrictMode 下 effect 会执行两次（创建 → 清理 → 再创建），
  // 两次的 X6 视图若共用同一个 DOM 容器会互相踩：前一次的 dispose 会把后一次
  // 已经插入的 <svg> 摘掉，只剩 div.x6-graph-background —— 表现为"画布一片空白"。
  // 每次创建独占一个子元素、dispose 时整体摘除，残留不可能影响下一次。
  const mount = document.createElement("div");
  mount.className = "gb-mount";
  mount.style.width = "100%";
  mount.style.height = "100%";
  container.appendChild(mount);

  const graph = new Graph({
    container: mount,
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

  graph.use(new Export());

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
    // 分组框必须计入包围盒：只算节点会漏掉框的外扩内边距与标题区，
    // 内容宽度算小 → 画布宽度不足 → 右侧的框和节点会被裁掉（用户报的"图很乱"）。
    for (const frame of Object.values(layout.groupBoxes ?? {})) {
      minX = Math.min(minX, frame.x);
      minY = Math.min(minY, frame.y);
      maxX = Math.max(maxX, frame.x + frame.w);
      maxY = Math.max(maxY, frame.y + frame.h);
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
  // 几何优先取布局产出（分区域拼接会给出簇框）；没有则由成员包围盒反算。
  if (preset.groups) {
    /** 框是否真的包住了它的成员（用节点中心判断，容差 1px）。 */
    const frameCoversMembers = (
      frame: { x: number; y: number; w: number; h: number },
      members: string[],
    ) =>
      members.every((id) => {
        const point = layout.positions[id];
        if (!point) return true;
        return (
          point.x >= frame.x - 1 &&
          point.x <= frame.x + frame.w + 1 &&
          point.y >= frame.y - 1 &&
          point.y <= frame.y + frame.h + 1
        );
      });

    const groups = [...(ir.groups ?? [])];
    // 边界按成员数降序绘制 → 大框在底层，小框叠上即嵌套视觉（020 §5.7）
    if (preset.groups === "boundary") {
      groups.sort((a, b) => b.members.length - a.members.length);
    }
    const laneHeight = preset.layout.laneHeight ?? 124;
    groups.forEach((group, index) => {
      const isLane = group.type === "lane";
      const isBoundary = ["region", "vpc", "security-group"].includes(group.type);
      let frame = layout.groupBoxes?.[group.id];
      if (frame && !frameCoversMembers(frame, group.members)) {
        // 布局产出的框与节点坐标不同源（分区域拼接的已知风险）→ 丢弃，
        // 退回按成员包围盒反算。宁可能力受限，也不能画出一个框不住成员的框。
        console.warn(`[GraphBlock] 分组框未包住成员，回退为成员包围盒：${group.id}`, frame);
        frame = undefined;
      }
      if (!frame) {
        let minX = Infinity;
        let minY = Infinity;
        let maxX = -Infinity;
        let maxY = -Infinity;
        for (const id of group.members) {
          const point = layout.positions[id];
          const member = ir.nodes.find((item) => item.id === id);
          if (!point || !member) continue;
          const size = nodeSize(member, nodeShapes.get(id) as string);
          minX = Math.min(minX, point.x - size.w / 2);
          maxX = Math.max(maxX, point.x + size.w / 2);
          minY = Math.min(minY, point.y - size.h / 2);
          maxY = Math.max(maxY, point.y + size.h / 2);
        }
        if (!Number.isFinite(minX)) return;
        const pad = isBoundary ? (group.type === "region" ? 22 : 12) : 16;
        frame = {
          x: minX - pad,
          y: minY - pad,
          w: maxX - minX + pad * 2,
          h: maxY - minY + pad * 2,
        };
      }
      if (isLane && box) {
        // 泳道横跨整幅：宽度取内容宽度，y 由泳道序号决定（与 lane 布局一致）
        frame = {
          x: box.minX - PADDING / 2,
          y: index * laneHeight + 5,
          w: box.maxX - box.minX + PADDING,
          h: laneHeight - 10,
        };
      }
      graph.addNode({
        id: `__group_${group.id}`,
        // 用自有形态（GROUP_FRAME_SHAPE）：内置 rect 的 label 带 refX/refY 居中语义，
        // 会把分组标题推到框的右下角
        shape: GROUP_FRAME_SHAPE,
        x: offset.x + frame.x,
        y: offset.y + frame.y,
        width: frame.w,
        height: frame.h,
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
          title: {
            text: group.label ?? "",
            // 框尺寸运行时才知道，这里按实际宽高换算（text 的原点是节点中心）
            x: 10 - frame.w / 2,
            y: 16 - frame.h / 2,
            textAnchor: "start",
            textVerticalAnchor: "middle",
            fill: theme.textSecondary,
            fontSize: 10.5,
            fontFamily: GRAPH_MONO_STACK,
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
      // 布局引擎给的是**中心点**，X6 的 node.x/y 是**左上角**——不减半身位
      // 会让每个节点整体右下偏移半个尺寸，进而逃出分组框（曾导致"图很乱"）。
      x: point.x - size.w / 2 + offset.x,
      y: point.y - size.h / 2 + offset.y,
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

  // ── 内容尺寸 + 适配缩放
  //
  // 策略：**按宽度等比适配**。内容比容器宽时整体缩小到刚好放得下，容器高度按
  // 缩放后的高度撑开——整幅图完整可见，不用横向或纵向拖拽（用户的直接诉求）。
  // 但缩放下限 MIN_FIT_SCALE 兜住可读性：字缩到 12.5px × 0.55 已经是极限，
  // 更宽的图宁可保持该比例并横向滚动（020 §11.3 的取舍在这里让步于完整可见）。
  const contentSize = box
    ? {
        width: Math.ceil(box.maxX - box.minX + PADDING * 2),
        height: Math.ceil(box.maxY - box.minY + PADDING * 2),
      }
    : { width: 320, height: 200 };

  const measure = () => {
    const available = container.clientWidth || contentSize.width;
    const byWidth = Math.min(1, available / contentSize.width);
    // 高度**不乘 byWidth**：图宽被缩小时高度也跟着缩会让画布变得又扁又矮
    // （3182 宽的图按 0.31 适配后只剩 161px 高）。高度只由内容高与上下限决定，
    // 宽度方向交给 zoomToFit 去适配。
    return {
      width: Math.ceil(contentSize.width * byWidth),
      height: Math.min(
        CANVAS_MAX_HEIGHT,
        Math.max(CANVAS_MIN_HEIGHT, Math.ceil(contentSize.height)),
      ),
    };
  };

  const resize = () => {
    const width = container.clientWidth || contentSize.width;
    const height = container.clientHeight || contentSize.height;
    if (width <= 0 || height <= 0) return;
    try {
      graph.resize(width, height);
      // 内容在任一方向超出可视区 → 双向适配，保证整幅图可见（不用拖拽查看）
      if (contentSize.width > width || contentSize.height > height) {
        // 用 zoomToFit 而非 zoom + centerContent：X6 里 zoom 的缩放基准点不易控制，
        // 实测会把内容推出视口（画布整片空白）。
        graph.zoomToFit({ padding: 8, minScale: MIN_FIT_SCALE, maxScale: 1 });
      } else {
        // 画布比内容高（下限抬高后很常见）→ 居中，避免整幅图贴着顶边
        graph.centerContent();
      }
    } catch (err) {
      console.warn("[GraphBlock] resize 失败:", err);
    }
  };

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
  //
  // 依据 X6 export 插件的真实行为（读过 es/plugin/export/index.js）：
  // - `viewBox` 默认就是**内容包围盒**、stage 的 transform 会被插件自己摘掉，
  //   所以导出天然是"完整内容 + 1:1"，不需要我们手动重置视口。
  // - 默认导出的 SVG `width/height` 是 `100%`，存成文件后没有父容器就没有尺寸
  //   → 必须 `preserveDimensions: true` 让尺寸写成实际内容宽高。
  // - PNG 的缩放倍数字段是 **`ratio`**（不是 pixelRatio，写错会一直是 1x、图很糊）。
  //
  // 仍需自己处理两件事：
  // 1. 流动层靠 CSS 类隐藏，而 CSS 不随导出文件走 → 用 inline style 隐藏；
  // 2. hover 的关联压暗（opacity .38）会被一起导出去 → 先清掉。
  /**
   * 等异步渲染队列落地。
   *
   * X6 默认 `async: true`：cell 是**分批进 DOM** 的，不是创建后立即全部就位。
   * 导出克隆的是"当前 SVG 里的元素"，若此刻队列还没 flush，导出就会缺内容
   * （实测：16 节点 15 边的图只导出 8 个 cell）。所以导出前先等到位。
   */
  const waitForRender = async (): Promise<void> => {
    const expected = ir.nodes.length + (ir.groups?.length ?? 0);
    for (let attempt = 0; attempt < 30; attempt += 1) {
      if (container.querySelectorAll(".x6-node").length >= expected) return;
      await new Promise((resolve) => {
        requestAnimationFrame(() => resolve(null));
      });
    }
  };

  const beginExport = (): (() => void) => {
    clearFocus();
    const hidden: SVGElement[] = [];
    container.querySelectorAll<SVGElement>(".x6-edge path:nth-of-type(2)").forEach((path) => {
      hidden.push(path);
      path.style.display = "none";
    });
    return () => {
      hidden.forEach((path) => {
        path.style.display = "";
      });
    };
  };

  /** 导出前后的流动开关与临时隐藏，收在一处避免遗漏恢复。 */
  const withExportScope = async <T>(run: () => T | Promise<T>): Promise<T> => {
    const wasFlow = flowEnabled;
    if (wasFlow) setFlow(false);
    await waitForRender(); // 等 cell 全部进 DOM，否则导出缺内容
    const restore = beginExport();
    try {
      return await run();
    } finally {
      restore();
      if (wasFlow) setFlow(true);
    }
  };

  /**
   * 导出范围 = 完整内容。内容坐标已从 PADDING 起，故原点为 (0,0)。
   * **必须显式传**：不传 viewBox/width/height 时，`toDataURL` 会用
   * `graph.getContentBBox()` 反推尺寸，实测退化成 1×1 —— PNG 导出一张
   * 148 字节的纯色空图。
   */
  const exportBox = {
    x: 0,
    y: 0,
    width: contentSize.width,
    height: contentSize.height,
  };

  const exportSVG = (): Promise<string> =>
    withExportScope(() =>
      graph.toSVGAsync({
        viewBox: exportBox,
        preserveDimensions: { width: exportBox.width, height: exportBox.height },
        copyStyles: true,
      }),
    );

  const exportPNG = (ratio = 2): Promise<string> =>
    withExportScope(() =>
      graph.toPNGAsync({
        viewBox: exportBox,
        width: exportBox.width,
        height: exportBox.height,
        ratio,
        backgroundColor: theme.surface,
        padding: 8,
      }),
    );

  const dispose = () => {
    stopDemo();
    animations.releaseFlowSlot();
    animations.disposeAll();
    scheduler.dispose();
    graph.dispose();
    // 摘掉本次独占的挂载点，绝不给下一次渲染留残留 DOM
    mount.remove();
  };

  // 历史消息：直渲染终态（零动画、不自动开流动）
  if (animate) replay();
  else container.classList.add("gb-static");

  return {
    contentSize,
    measure,
    resize,
    replay,
    setFlow,
    playDemo,
    stopDemo,
    exportSVG,
    exportPNG,
    dispose,
  };
}
