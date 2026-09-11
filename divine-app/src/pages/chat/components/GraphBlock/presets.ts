/**
 * presets —— ScenarioPreset 常量表 + Resolver。
 *
 * 这是整个方案的支点（004 决策 1）：**「画什么」与「怎么画」在这里分开**。
 * IR 只说 `kind` + 拓扑 + 语义；布局引擎、节点形态、路由、交互等级、动效、
 * 上限、视口策略全部由这张表决定。
 *
 * 因此——**新增一个场景 = 表里加一行**，不改 schema、不改后端、不改渲染器
 * （P2.5 的验收标准就是这条）。
 *
 * 表内容对应 docs/design/020-x6-multi-scenario-20260908.md §4。
 */

import type { GraphKind, GraphNode, NodeRole } from "./GraphIR";

export type LayoutEngine =
  "dagre" | "force" | "compactBox" | "mindmap" | "swimlane" | "lifeline" | "fishbone" | "timeline";

export type LayoutDirection = "TB" | "LR" | "RL" | "BT";

export interface LayoutSpec {
  engine: LayoutEngine;
  direction?: LayoutDirection;
  rankSep?: number;
  nodeSep?: number;
  /** swimlane：泳道带高度 */
  laneHeight?: number;
  /** concept：画幅（力导收敛后归一化到该比例，保证圆间距） */
  aspect?: number;
}

/** 边族：路由 + 连线 + 箭头形态（020 §5.2）。 */
export interface EdgeSpec {
  router: "orth" | "normal";
  connector: "rounded" | "smooth";
  arrow: "solid" | "hollow" | "none";
}

/** 交互等级决定加载哪些 X6 插件（020 §6）。 */
export type InteractionLevel = "L0" | "L1" | "L2";

export type GraphCapability = "export" | "flow" | "play" | "fold" | "minimap" | "zoom";

export interface MotionSpec {
  /** 入场 stagger（ms） */
  stagger: number;
  /** 持续动效：antline 流动（仅标记 flow 的边） */
  flow: boolean;
  /** 是否有 demoPath 播放 */
  play: boolean;
}

export interface ScenarioPreset {
  kind: GraphKind;
  /** 场景中文名（容器 aria-label / 工具条标题） */
  label: string;
  layout: LayoutSpec;
  /** role → 形态（缺省走 DEFAULT_ROLE_SHAPES） */
  shapes?: Partial<Record<NodeRole, string>>;
  /** 该场景的统一形态（富节点场景用，覆盖 role 映射） */
  defaultShape?: string;
  edges: EdgeSpec;
  groups: "lane" | "cluster" | "boundary" | null;
  level: InteractionLevel;
  motion: MotionSpec;
  limit: { nodes: number };
  view: "fit" | "center" | "scroll";
  capabilities: GraphCapability[];
  /** 底部图例通道（arch / sequence 等） */
  legend?: boolean;
  /** 类别色带（arch / workflow 类叙事） */
  categorical?: boolean;
  /** 泳道是否画成虚线圆角框（对齐 021 基准） */
  frameLanes?: boolean;
}

/** role → 默认形态（020 §5.1 节点形态族）。 */
export const DEFAULT_ROLE_SHAPES: Record<NodeRole, string> = {
  start: "pill",
  end: "pill",
  process: "rounded",
  decision: "diamond",
  data: "cylinder",
  entity: "section",
  state: "stateNode",
  milestone: "milestone",
  member: "rounded",
};

const BASE_CAPS: GraphCapability[] = ["export", "zoom"];

/**
 * 15 行场景表。行序与 020 §4 一致，便于对照。
 */
export const PRESETS: Record<GraphKind, ScenarioPreset> = {
  flow: {
    kind: "flow",
    label: "流程图",
    layout: { engine: "dagre", direction: "LR", rankSep: 56, nodeSep: 28 },
    edges: { router: "orth", connector: "rounded", arrow: "solid" },
    groups: null,
    level: "L2",
    motion: { stagger: 45, flow: true, play: true },
    limit: { nodes: 80 },
    view: "fit",
    capabilities: [...BASE_CAPS, "flow", "play"],
  },
  dag: {
    kind: "dag",
    label: "任务编排",
    layout: { engine: "dagre", direction: "TB", rankSep: 64, nodeSep: 32 },
    defaultShape: "dagNode",
    edges: { router: "orth", connector: "rounded", arrow: "solid" },
    groups: "cluster",
    level: "L2",
    motion: { stagger: 45, flow: true, play: false },
    limit: { nodes: 120 },
    view: "fit",
    capabilities: [...BASE_CAPS, "flow"],
  },
  dataflow: {
    kind: "dataflow",
    label: "数据加工链路",
    layout: { engine: "dagre", direction: "LR", rankSep: 64, nodeSep: 32 },
    defaultShape: "dpNode",
    edges: { router: "orth", connector: "rounded", arrow: "solid" },
    groups: null,
    level: "L2",
    motion: { stagger: 45, flow: true, play: false },
    limit: { nodes: 80 },
    view: "fit",
    capabilities: [...BASE_CAPS, "flow"],
  },
  state: {
    kind: "state",
    label: "状态机",
    layout: { engine: "dagre", direction: "LR", rankSep: 68, nodeSep: 40 },
    shapes: { state: "stateNode" },
    edges: { router: "normal", connector: "smooth", arrow: "solid" },
    groups: null,
    level: "L2",
    motion: { stagger: 45, flow: false, play: true },
    limit: { nodes: 40 },
    view: "center",
    capabilities: [...BASE_CAPS, "play"],
  },
  org: {
    kind: "org",
    label: "组织架构",
    layout: { engine: "compactBox", direction: "TB", rankSep: 56, nodeSep: 28 },
    defaultShape: "orgNode",
    edges: { router: "orth", connector: "rounded", arrow: "none" },
    groups: null,
    level: "L1",
    motion: { stagger: 35, flow: false, play: false },
    limit: { nodes: 150 },
    view: "fit",
    capabilities: [...BASE_CAPS, "fold", "minimap"],
  },
  mindmap: {
    kind: "mindmap",
    label: "思维导图",
    layout: { engine: "mindmap", direction: "LR", rankSep: 54, nodeSep: 24 },
    defaultShape: "mapBranch",
    edges: { router: "normal", connector: "smooth", arrow: "none" },
    groups: null,
    level: "L1",
    motion: { stagger: 35, flow: false, play: false },
    limit: { nodes: 120 },
    view: "fit",
    capabilities: [...BASE_CAPS, "fold", "minimap"],
  },
  topology: {
    kind: "topology",
    label: "系统拓扑",
    layout: { engine: "dagre", direction: "TB", rankSep: 72, nodeSep: 36 },
    shapes: { process: "rounded", data: "cylinder", entity: "cylinder" },
    edges: { router: "orth", connector: "rounded", arrow: "solid" },
    groups: "cluster",
    level: "L1",
    motion: { stagger: 45, flow: true, play: false },
    limit: { nodes: 100 },
    view: "fit",
    capabilities: [...BASE_CAPS, "flow", "minimap"],
  },
  arch: {
    kind: "arch",
    label: "系统架构图",
    layout: { engine: "dagre", direction: "TB", rankSep: 76, nodeSep: 40 },
    defaultShape: "archNode",
    edges: { router: "orth", connector: "rounded", arrow: "solid" },
    groups: "boundary",
    level: "L1",
    motion: { stagger: 45, flow: true, play: false },
    limit: { nodes: 60 },
    view: "fit",
    capabilities: [...BASE_CAPS, "flow", "minimap"],
    legend: true,
    categorical: true,
  },
  er: {
    kind: "er",
    label: "实体关系",
    layout: { engine: "force", rankSep: 60, nodeSep: 40, aspect: 1.4 },
    shapes: { entity: "section", data: "section" },
    edges: { router: "normal", connector: "smooth", arrow: "none" },
    groups: null,
    level: "L0",
    motion: { stagger: 0, flow: false, play: false },
    limit: { nodes: 24 },
    view: "fit",
    capabilities: [...BASE_CAPS],
  },
  swimlane: {
    kind: "swimlane",
    label: "跨职能流程",
    layout: { engine: "swimlane", direction: "LR", rankSep: 60, nodeSep: 32, laneHeight: 124 },
    defaultShape: "archNode",
    edges: { router: "orth", connector: "rounded", arrow: "solid" },
    groups: "lane",
    level: "L2",
    motion: { stagger: 45, flow: true, play: true },
    limit: { nodes: 60 },
    view: "scroll",
    capabilities: [...BASE_CAPS, "flow", "play"],
    frameLanes: true,
    categorical: true,
  },
  sequence: {
    kind: "sequence",
    label: "往返时序",
    layout: { engine: "lifeline", rankSep: 186, nodeSep: 44 },
    defaultShape: "archNode",
    edges: { router: "normal", connector: "smooth", arrow: "solid" },
    groups: null,
    level: "L1",
    motion: { stagger: 45, flow: false, play: true },
    limit: { nodes: 12 },
    view: "fit",
    capabilities: [...BASE_CAPS, "play", "minimap"],
    legend: true,
  },
  concept: {
    kind: "concept",
    label: "知识图谱",
    layout: { engine: "force", rankSep: 60, nodeSep: 48, aspect: 1.4 },
    defaultShape: "conceptNode",
    edges: { router: "normal", connector: "smooth", arrow: "none" },
    groups: null,
    level: "L1",
    motion: { stagger: 0, flow: false, play: false },
    limit: { nodes: 80 },
    view: "fit",
    capabilities: [...BASE_CAPS, "minimap"],
    legend: true,
  },
  class: {
    kind: "class",
    label: "类图",
    layout: { engine: "dagre", direction: "LR", rankSep: 72, nodeSep: 36 },
    shapes: { entity: "section", data: "section" },
    edges: { router: "orth", connector: "rounded", arrow: "hollow" },
    groups: null,
    level: "L0",
    motion: { stagger: 45, flow: false, play: false },
    limit: { nodes: 20 },
    view: "fit",
    capabilities: [...BASE_CAPS],
  },
  fishbone: {
    kind: "fishbone",
    label: "因果分析",
    layout: { engine: "fishbone", rankSep: 56, nodeSep: 32 },
    edges: { router: "normal", connector: "smooth", arrow: "solid" },
    groups: null,
    level: "L0",
    motion: { stagger: 45, flow: false, play: false },
    limit: { nodes: 40 },
    view: "fit",
    capabilities: [...BASE_CAPS],
  },
  timeline: {
    kind: "timeline",
    label: "时间线",
    layout: { engine: "timeline", rankSep: 88, nodeSep: 28 },
    defaultShape: "milestone",
    edges: { router: "normal", connector: "smooth", arrow: "none" },
    groups: null,
    level: "L0",
    motion: { stagger: 45, flow: false, play: false },
    limit: { nodes: 30 },
    view: "fit",
    capabilities: [...BASE_CAPS],
  },
};

/** 未知 kind 走这里——不静默当 flow，而是明确回退并告警。 */
const FALLBACK_KIND: GraphKind = "flow";

export function resolvePreset(kind: GraphKind): ScenarioPreset {
  const preset = PRESETS[kind];
  if (preset) return preset;
  console.warn(`[GraphBlock] 未知场景 ${kind}，按 ${FALLBACK_KIND} 兜底渲染`);
  return PRESETS[FALLBACK_KIND];
}

/** 节点形态解析：场景统一形态 > role 映射 > process 默认。 */
export function shapeForNode(preset: ScenarioPreset, node: GraphNode): string {
  if (node.pseudo) return "statePseudo";
  // mindmap 三级形态：root / branch / leaf 由层级决定
  if (preset.kind === "mindmap") {
    const depth = node.parent ? 2 : 1;
    if (depth === 2) return "mapLeaf";
    return node.role === "start" || node.role === "process" ? "mapRoot" : "mapBranch";
  }
  if (preset.defaultShape) return preset.defaultShape;
  const role = node.role ?? "process";
  return preset.shapes?.[role] ?? DEFAULT_ROLE_SHAPES[role] ?? "rounded";
}
