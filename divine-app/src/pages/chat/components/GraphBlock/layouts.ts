/**
 * layouts —— 布局引擎适配层。
 *
 * 用 `@antv/layout` 一套库覆盖大部分场景（020 §4）：
 * dagre（含 4 个方向）、force、compactBox、mindmap；
 * fishbone / timeline / sequence 无通用算法，各写一个自定义函数。
 *
 * 布局**全流程只跑一次**（完整 IR 到达后），不做增量布局（004 性能要点）。
 * 力导结果在收敛后固化坐标——历史回放不再跑力导（020 §7 硬约束 4）。
 */

import type { GraphIR, GraphNode } from "./GraphIR";
import type { LayoutSpec, ScenarioPreset } from "./presets";

export interface LayoutResult {
  positions: Record<string, { x: number; y: number }>;
  /** 力导/时序等需要额外几何信息的场景回传（如生命线 extBottom） */
  extras?: { lifelineBottom?: number };
}

type SizeOf = (node: GraphNode) => { w: number; h: number };

/* eslint-disable @typescript-eslint/no-explicit-any -- 动态 import 的 X6/Layout 命名空间 */

const FALLBACK_GAP = 28;

/** dagre / 层次布局：把 IR 交给 @antv/layout 的 DagreLayout。 */
function dagreLayout(layoutNs: any, ir: GraphIR, spec: LayoutSpec, sizeOf: SizeOf): LayoutResult {
  const DagreLayout = layoutNs.DagreLayout ?? layoutNs.default?.DagreLayout;
  const nodes = ir.nodes.map((node) => {
    const { w, h } = sizeOf(node);
    return { id: node.id, size: [w, h] };
  });
  const edges = ir.edges.map((edge) => ({ source: edge.source, target: edge.target }));

  if (!DagreLayout) return gridFallback(ir, sizeOf);

  const layout = new DagreLayout({
    type: "dagre",
    rankdir: spec.direction ?? "TB",
    ranksep: spec.rankSep ?? 56,
    nodesep: spec.nodeSep ?? FALLBACK_GAP,
    controlPoints: false,
  });
  const result = layout.layout({ nodes, edges } as any) as any;
  const positions: Record<string, { x: number; y: number }> = {};
  for (const item of result.nodes ?? []) {
    // @antv/layout 返回的是中心点坐标
    positions[item.id] = { x: item.x ?? 0, y: item.y ?? 0 };
  }
  return { positions };
}

/** 力导：concept / er。坐标直接固化使用。 */
function forceLayout(layoutNs: any, ir: GraphIR, spec: LayoutSpec, sizeOf: SizeOf): LayoutResult {
  const ForceLayout = layoutNs.ForceLayout ?? layoutNs.default?.ForceLayout;
  if (!ForceLayout) return dagreLayout(layoutNs, ir, spec, sizeOf);
  const nodes = ir.nodes.map((node) => {
    const { w, h } = sizeOf(node);
    return { id: node.id, size: [w, h] };
  });
  const edges = ir.edges.map((edge) => ({ source: edge.source, target: edge.target }));
  const layout = new ForceLayout({
    type: "force",
    linkDistance: spec.rankSep ?? 60,
    nodeStrength: -180,
    collideStrength: 1,
    alphaDecay: 0.03,
    // 力导是随机的，固定随机源让同一份 IR 每次得到同一张图（可重放）
    random: () => 0.5,
  });
  const result = layout.layout({ nodes, edges } as any) as any;
  const positions: Record<string, { x: number; y: number }> = {};
  for (const item of result.nodes ?? []) {
    positions[item.id] = { x: item.x ?? 0, y: item.y ?? 0 };
  }
  return { positions };
}

/** 层次树：compactBox（org）/ mindmap。 */
function treeLayout(
  layoutNs: any,
  ir: GraphIR,
  spec: LayoutSpec,
  sizeOf: SizeOf,
  engine: "compactBox" | "mindmap",
): LayoutResult {
  const TreeLayout = layoutNs.CompactBoxLayout ?? layoutNs.default?.CompactBoxLayout;
  if (!TreeLayout) return dagreLayout(layoutNs, ir, spec, sizeOf);

  // 由 parent 字段或边推导父子关系（IR 两种写法都支持）
  const childOf = new Map<string, string>();
  for (const node of ir.nodes) {
    if (node.parent) childOf.set(node.id, node.parent);
  }
  for (const edge of ir.edges) {
    if (!childOf.has(edge.target)) childOf.set(edge.target, edge.source);
  }
  const roots = ir.nodes.filter((node) => !childOf.has(node.id));
  const sizeMap = new Map(ir.nodes.map((node) => [node.id, sizeOf(node)]));

  const build = (id: string, seen: Set<string>): any => {
    const size = sizeMap.get(id) ?? { w: 136, h: 46 };
    const children = ir.nodes
      .filter((node) => childOf.get(node.id) === id && !seen.has(node.id))
      .map((node) => build(node.id, new Set([...seen, id])));
    return { id, width: size.w, height: size.h, children };
  };

  const rootsData = roots.map((node) => build(node.id, new Set()));
  if (!rootsData.length) return dagreLayout(layoutNs, ir, spec, sizeOf);

  const layout = new TreeLayout({
    type: engine === "mindmap" ? "mindmap" : "compactBox",
    direction: engine === "mindmap" ? "H" : "TB",
    getId: (d: any) => d.id,
    getWidth: (d: any) => d.width,
    getHeight: (d: any) => d.height,
    getHGap: () => spec.nodeSep ?? 24,
    getVGap: () => spec.rankSep ?? 56,
  });

  const positions: Record<string, { x: number; y: number }> = {};
  const walk = (data: any, offsetX: number) => {
    const result = layout.layout(data) as any;
    const traverse = (item: any) => {
      if (!item) return;
      positions[item.data?.id ?? item.id] = {
        x: (item.x ?? 0) + offsetX,
        y: item.y ?? 0,
      };
      for (const child of item.children ?? []) traverse(child);
    };
    traverse(result);
  };
  let offset = 0;
  for (const root of rootsData) {
    walk(root, offset);
    offset += 320;
  }
  return { positions };
}

/** 泳道：先做 dagre LR，再按 lane 归属把 y 压到对应泳道带。 */
function swimlaneLayout(
  layoutNs: any,
  ir: GraphIR,
  spec: LayoutSpec,
  sizeOf: SizeOf,
): LayoutResult {
  const base = dagreLayout(layoutNs, ir, { ...spec, direction: "LR" }, sizeOf);
  const lanes = (ir.groups ?? []).filter((group) => group.type === "lane");
  if (!lanes.length) return base;
  const laneIndex = new Map(lanes.map((lane, index) => [lane.id, index]));
  const laneHeight = spec.laneHeight ?? 124;
  const positions: Record<string, { x: number; y: number }> = {};
  for (const node of ir.nodes) {
    const point = base.positions[node.id] ?? { x: 0, y: 0 };
    const index = node.lane != null ? (laneIndex.get(node.lane) ?? 0) : 0;
    positions[node.id] = {
      x: point.x,
      y: index * laneHeight + laneHeight / 2,
    };
  }
  return { positions, extras: { lifelineBottom: lanes.length * laneHeight } };
}

/** 时序：参与者顶部横排，消息按数组顺序排水平线（020 §5.8）。 */
function lifelineLayout(ir: GraphIR, spec: LayoutSpec, sizeOf: SizeOf): LayoutResult {
  const colWidth = spec.rankSep ?? 186;
  const rowHeight = spec.nodeSep ?? 44;
  const positions: Record<string, { x: number; y: number }> = {};
  ir.nodes.forEach((node, index) => {
    const { w } = sizeOf(node);
    positions[node.id] = { x: index * colWidth + w / 2, y: 26 };
  });
  const bottom = 26 + 50 + Math.max(0, ir.edges.length - 1) * rowHeight + 26;
  return { positions, extras: { lifelineBottom: bottom } };
}

/** 鱼骨：中轴 + 左右交替斜肋。 */
function fishboneLayout(ir: GraphIR, spec: LayoutSpec, sizeOf: SizeOf): LayoutResult {
  const positions: Record<string, { x: number; y: number }> = {};
  const spine = ir.nodes[0];
  const ribs = ir.nodes.slice(1);
  if (spine) positions[spine.id] = { x: 0, y: 0 };
  const gap = spec.rankSep ?? 56;
  ribs.forEach((node, index) => {
    const side = index % 2 === 0 ? -1 : 1;
    const column = Math.floor(index / 2);
    const { w, h } = sizeOf(node);
    positions[node.id] = {
      x: -40 - column * (gap + 90),
      y: side * (60 + (index % 2 === 0 ? h : h)),
    };
    void w;
  });
  return { positions };
}

/** 时间线：单轴 + 上下交错。 */
function timelineLayout(ir: GraphIR, spec: LayoutSpec, sizeOf: SizeOf): LayoutResult {
  const positions: Record<string, { x: number; y: number }> = {};
  const gap = spec.rankSep ?? 88;
  ir.nodes.forEach((node, index) => {
    const { w } = sizeOf(node);
    positions[node.id] = {
      x: index * gap + w / 2,
      y: index % 2 === 0 ? -46 : 46,
    };
  });
  return { positions };
}

/** 兜底：网格排布（布局引擎缺失时也要出图，而不是白屏）。 */
function gridFallback(ir: GraphIR, sizeOf: SizeOf): LayoutResult {
  const positions: Record<string, { x: number; y: number }> = {};
  const columns = Math.max(1, Math.ceil(Math.sqrt(ir.nodes.length)));
  ir.nodes.forEach((node, index) => {
    const { w, h } = sizeOf(node);
    const col = index % columns;
    const row = Math.floor(index / columns);
    positions[node.id] = { x: col * (w + 48) + w / 2, y: row * (h + 56) + h / 2 };
  });
  return { positions };
}

/**
 * 按 Preset 计算布局。engine 未实现时回退 dagre（P2.5 逐行补齐），
 * 保证"加场景 = 加一行"不会因为缺布局而崩。
 */
export function computeLayout(
  layoutNs: any,
  ir: GraphIR,
  preset: ScenarioPreset,
  sizeOf: SizeOf,
): LayoutResult {
  const spec = preset.layout;
  switch (spec.engine) {
    case "dagre":
      return dagreLayout(layoutNs, ir, spec, sizeOf);
    case "force":
      return forceLayout(layoutNs, ir, spec, sizeOf);
    case "compactBox":
    case "mindmap":
      return treeLayout(layoutNs, ir, spec, sizeOf, spec.engine);
    case "swimlane":
      return swimlaneLayout(layoutNs, ir, spec, sizeOf);
    case "lifeline":
      return lifelineLayout(ir, spec, sizeOf);
    case "fishbone":
      return fishboneLayout(ir, spec, sizeOf);
    case "timeline":
      return timelineLayout(ir, spec, sizeOf);
    default:
      console.warn(`[GraphBlock] 未实现的布局引擎 ${String(spec.engine)}，回退 dagre`);
      return dagreLayout(layoutNs, ir, spec, sizeOf);
  }
}
