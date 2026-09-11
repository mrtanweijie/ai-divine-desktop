/**
 * GraphIR —— 前端侧的类型与白名单校验。
 *
 * 后端 `app/tools/graph/validator.py` 是权威校验；这里是**纵深防御**：
 * IR 来自 LLM、且会经 tool_runs 持久化后在历史回放时再次读取，任何一次落库
 * 或手工改动都可能带入脏数据。渲染器必须能安全地拒绝它，而不是把任意
 * SVG attrs 注入到画布上。
 *
 * 契约文件：`divine-server/app/tools/graph/graph_ir.schema.json`
 * 设计文档：docs/design/020-x6-multi-scenario-20260908.md §3
 */

/** 15 个场景（封闭枚举）——与后端 GRAPH_KINDS 一一对应。 */
export const GRAPH_KINDS = [
  "flow",
  "dag",
  "dataflow",
  "state",
  "org",
  "mindmap",
  "topology",
  "arch",
  "er",
  "swimlane",
  "sequence",
  "concept",
  "class",
  "fishbone",
  "timeline",
] as const;

export type GraphKind = (typeof GRAPH_KINDS)[number];

/** 场景中文名：用于容器 aria-label 与回退标题。 */
export const KIND_LABELS: Record<GraphKind, string> = {
  flow: "流程图",
  dag: "任务编排",
  dataflow: "数据加工链路",
  state: "状态机",
  org: "组织架构",
  mindmap: "思维导图",
  topology: "系统拓扑",
  arch: "系统架构图",
  er: "实体关系",
  swimlane: "跨职能流程",
  sequence: "往返时序",
  concept: "知识图谱",
  class: "类图",
  fishbone: "因果分析",
  timeline: "时间线",
};

const KNOWN_KINDS = new Set<string>(GRAPH_KINDS);

export const NODE_ROLES = [
  "start",
  "end",
  "process",
  "decision",
  "data",
  "entity",
  "state",
  "milestone",
  "member",
] as const;

export type NodeRole = (typeof NODE_ROLES)[number];

export const TONES = ["neutral", "info", "success", "warning", "error"] as const;
export type GraphTone = (typeof TONES)[number];

export const NODE_STATES = ["pending", "running", "success", "failed"] as const;
export type NodeState = (typeof NODE_STATES)[number];

/** state 映射到 tone，不引入第二套语义色（020 §5.5）。 */
export const STATE_TONE: Record<NodeState, GraphTone> = {
  pending: "neutral",
  running: "info",
  success: "success",
  failed: "error",
};

export const PSEUDO_STATES = ["initial", "final", "choice"] as const;
export type PseudoState = (typeof PSEUDO_STATES)[number];

export const EDGE_STYLES = ["solid", "dashed", "dotted"] as const;
export type EdgeStyle = (typeof EDGE_STYLES)[number];

export const GROUP_TYPES = ["lane", "cluster", "combo", "region", "vpc", "security-group"] as const;
export type GroupType = (typeof GROUP_TYPES)[number];

export interface GraphNode {
  id: string;
  label?: string;
  role?: NodeRole;
  tone?: GraphTone;
  note?: string;
  badge?: string;
  /** dag / dataflow：执行状态 */
  state?: NodeState;
  /** dag / dataflow：内联图标名 */
  icon?: string;
  /** state：伪状态（无 label） */
  pseudo?: PseudoState;
  /** state：当前激活态，全图最多 1 个 */
  active?: boolean;
  /** org：职位 / 编制 */
  role_desc?: string;
  /** org：直属子节点数 */
  count?: number;
  /** concept / arch：类型枚举 */
  type?: string;
  /** arch / 工作流：类别名（色由前端按首现顺序分配） */
  category?: string;
  /** arch：技术栈 / 端口副行 */
  sublabel?: string;
  /** arch：右上角徽标 */
  tag?: string;
  /** swimlane：所属泳道 id */
  lane?: string;
  /** 层次归属（org / mindmap） */
  parent?: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  kind?: string;
  tone?: GraphTone;
  style?: EdgeStyle;
  flow?: { mode?: "antline" | "pulse"; tone?: GraphTone; speed?: number };
}

export interface GraphGroup {
  id: string;
  label?: string;
  type: GroupType;
  members: string[];
}

export interface GraphIR {
  kind: GraphKind;
  meta?: { title?: string; summary?: string };
  nodes: GraphNode[];
  edges: GraphEdge[];
  groups?: GraphGroup[];
  demoPath?: string[];
}

/** 每层允许的字段——与后端白名单一致（未知键即拒绝）。 */
const TOP_KEYS = new Set(["kind", "meta", "nodes", "edges", "groups", "demoPath"]);
const NODE_KEYS = new Set([
  "id",
  "label",
  "role",
  "tone",
  "note",
  "badge",
  "state",
  "icon",
  "pseudo",
  "active",
  "role_desc",
  "count",
  "type",
  "category",
  "sublabel",
  "tag",
  "lane",
  "parent",
]);
const EDGE_KEYS = new Set(["id", "source", "target", "label", "kind", "tone", "style", "flow"]);
const GROUP_KEYS = new Set(["id", "label", "type", "members"]);

/** 危险键：原型污染与事件处理器注入。 */
const DANGEROUS_KEYS = new Set(["__proto__", "constructor", "prototype"]);
/** 后端已拒绝的几何 / 色值键，前端再挡一次。 */
const FORBIDDEN_KEYS = new Set([
  "x",
  "y",
  "w",
  "h",
  "width",
  "height",
  "pos",
  "size",
  "via",
  "fromSide",
  "toSide",
  "bc",
  "color",
  "fill",
  "stroke",
  "direction",
  "shape",
  "layout",
]);

export type GraphIRParseResult = { ok: true; ir: GraphIR } | { ok: false; reason: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 递归扫描禁用键（几何 / 色值 / 注入）。 */
function findForbidden(value: unknown, path: string): string | null {
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      const found = findForbidden(value[index], `${path}[${index}]`);
      if (found) return found;
    }
    return null;
  }
  if (!isRecord(value)) return null;
  for (const [key, item] of Object.entries(value)) {
    const here = path ? `${path}.${key}` : key;
    if (DANGEROUS_KEYS.has(key) || key.toLowerCase().startsWith("on")) {
      return `禁止的键名 ${here}`;
    }
    if (FORBIDDEN_KEYS.has(key)) return `禁止的字段 ${here}`;
    const found = findForbidden(item, here);
    if (found) return found;
  }
  return null;
}

function checkKeys(
  value: Record<string, unknown>,
  allowed: Set<string>,
  path: string,
): string | null {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) return `${path}.${key} 不是允许的字段`;
  }
  return null;
}

/**
 * 校验并归一化一份 GraphIR。失败时返回原因（调用方降级为错误提示，
 * 绝不尝试"尽力渲染"——半张错误的图比明确的失败更糟）。
 */
export function parseGraphIR(raw: unknown): GraphIRParseResult {
  if (!isRecord(raw)) return { ok: false, reason: "IR 不是对象" };

  const forbidden = findForbidden(raw, "");
  if (forbidden) return { ok: false, reason: forbidden };

  const unknownTop = checkKeys(raw, TOP_KEYS, "$");
  if (unknownTop) return { ok: false, reason: unknownTop };

  const kind = raw.kind;
  if (typeof kind !== "string" || !KNOWN_KINDS.has(kind)) {
    return { ok: false, reason: `未知场景 ${String(kind)}` };
  }

  const rawNodes = raw.nodes;
  if (!Array.isArray(rawNodes) || rawNodes.length === 0) {
    return { ok: false, reason: "nodes 为空" };
  }

  const nodes: GraphNode[] = [];
  const ids = new Set<string>();
  for (let index = 0; index < rawNodes.length; index += 1) {
    const item = rawNodes[index];
    if (!isRecord(item)) return { ok: false, reason: `nodes[${index}] 不是对象` };
    const badKey = checkKeys(item, NODE_KEYS, `$.nodes[${index}]`);
    if (badKey) return { ok: false, reason: badKey };
    const id = item.id;
    if (typeof id !== "string" || !id) {
      return { ok: false, reason: `nodes[${index}].id 缺失` };
    }
    if (ids.has(id)) return { ok: false, reason: `节点 id 重复：${id}` };
    ids.add(id);
    nodes.push({
      ...(item as unknown as GraphNode),
      id,
      role: typeof item.role === "string" ? (item.role as NodeRole) : undefined,
      tone: typeof item.tone === "string" ? (item.tone as GraphTone) : undefined,
      state: typeof item.state === "string" ? (item.state as NodeState) : undefined,
      pseudo: typeof item.pseudo === "string" ? (item.pseudo as PseudoState) : undefined,
    });
  }

  const rawEdges = Array.isArray(raw.edges) ? raw.edges : [];
  const edges: GraphEdge[] = [];
  for (let index = 0; index < rawEdges.length; index += 1) {
    const item = rawEdges[index];
    if (!isRecord(item)) return { ok: false, reason: `edges[${index}] 不是对象` };
    const badKey = checkKeys(item, EDGE_KEYS, `$.edges[${index}]`);
    if (badKey) return { ok: false, reason: badKey };
    const source = item.source;
    const target = item.target;
    if (typeof source !== "string" || typeof target !== "string") {
      return { ok: false, reason: `edges[${index}] 缺少 source/target` };
    }
    if (!ids.has(source) || !ids.has(target)) {
      return { ok: false, reason: `edges[${index}] 引用了不存在的节点` };
    }
    edges.push({
      ...(item as unknown as GraphEdge),
      id: typeof item.id === "string" && item.id ? item.id : `e${index + 1}`,
      source,
      target,
    });
  }

  const groups: GraphGroup[] = [];
  if (Array.isArray(raw.groups)) {
    for (let index = 0; index < raw.groups.length; index += 1) {
      const item = raw.groups[index];
      if (!isRecord(item)) return { ok: false, reason: `groups[${index}] 不是对象` };
      const badKey = checkKeys(item, GROUP_KEYS, `$.groups[${index}]`);
      if (badKey) return { ok: false, reason: badKey };
      const type = item.type;
      const members = Array.isArray(item.members) ? item.members : [];
      if (typeof item.id !== "string" || typeof type !== "string") {
        return { ok: false, reason: `groups[${index}] 缺少 id/type` };
      }
      const validMembers = members.filter(
        (member): member is string => typeof member === "string" && ids.has(member),
      );
      groups.push({
        id: item.id,
        label: typeof item.label === "string" ? item.label : undefined,
        type: type as GroupType,
        members: validMembers,
      });
    }
  }

  const demoPath = Array.isArray(raw.demoPath)
    ? raw.demoPath.filter((step): step is string => typeof step === "string" && ids.has(step))
    : undefined;

  const meta = isRecord(raw.meta)
    ? {
        title: typeof raw.meta.title === "string" ? raw.meta.title : undefined,
        summary: typeof raw.meta.summary === "string" ? raw.meta.summary : undefined,
      }
    : undefined;

  return {
    ok: true,
    ir: {
      kind: kind as GraphKind,
      meta,
      nodes,
      edges,
      groups: groups.length ? groups : undefined,
      demoPath: demoPath?.length ? demoPath : undefined,
    },
  };
}

/** 从 tool 结果里取 GraphIR 的入口在 `MessageItem/MessageHelpers.tsx`
 * （`graphIRFromResult`），与 `chartOptionFromResult` 放在一起——
 * 那里是"工具结果 → 渲染载荷"的统一提取层。这里只负责校验。
 */

/** 归一化后的节点 tone（state 优先于 tone，见 020 §5.5）。 */
export function nodeTone(node: GraphNode): GraphTone {
  if (node.state) return STATE_TONE[node.state];
  return node.tone ?? "neutral";
}
