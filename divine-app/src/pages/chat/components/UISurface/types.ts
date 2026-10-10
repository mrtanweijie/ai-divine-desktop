/**
 * A2UI 面板的前端类型镜像（纵深防御 L3）。
 *
 * 设计文档：`docs/design/028-a2ui-integration-20261009.md` §4 / §9.1。
 *
 * **真源在后端** `divine-server/app/tools/ui/catalog.py`，本文件是**手工镜像**
 * （跨语言，不共享代码），靠后端 `tests/test_render_ui.py` 的快照与
 * `divine_catalog.json` 对齐 —— 与 GraphIR 完全同范式
 * （`app/tools/graph/schema.py` ↔ `GraphBlock/GraphIR.ts`）。
 *
 * 三条铁律（044 §2.3 / §9.4）：
 * 1. IR 只描述「展示什么 + 能做什么」，**不描述长什么样**：禁坐标 / 色值 /
 *    样式 / HTML / 脚本；颜色只能用 `tone` 语义色。
 * 2. 前端只认这里声明的组件与属性，其余一律裁剪或拒绝（后端已硬拒，
 *    这里是防御后端被绕过或版本漂移的第二道闸）。
 * 3. 主题（深浅色）由本项目的 theme 决定，**不读面板传来的任何样式字段**。
 */

import type { ReactNode } from "react";
import type { GraphIR } from "@/pages/chat/components/GraphBlock/GraphIR";

// ---------------------------------------------------------------------------
// 闭集枚举（对应 catalog.py 的 TONES / GAPS / …）
// ---------------------------------------------------------------------------

/** 语义色。**只允许语义，不允许色值**（深浅色由 theme 决定）。 */
export type UITone = "default" | "primary" | "success" | "warning" | "danger";
export type UIGap = "none" | "sm" | "md" | "lg";
export type UIAlign = "start" | "center" | "end" | "stretch";
export type UIJustify = "start" | "center" | "end" | "between";
export type UITextVariant = "h1" | "h2" | "h3" | "h4" | "body" | "caption";
export type UIButtonVariant = "primary" | "ghost" | "danger";
export type UIOrientation = "horizontal" | "vertical";
export type UIStepStatus = "pending" | "active" | "done" | "error";

/** 面板状态：live=可交互（本次回合），closed=历史回放（只读）。 */
export type UISurfaceStatus = "live" | "closed";

// ---------------------------------------------------------------------------
// 数据绑定与动作
// ---------------------------------------------------------------------------

/** 数据绑定的**唯一形式**：`{"path": "/a/b"}`（RFC 6901 JSON Pointer 子集）。 */
export interface UIBinding {
  path: string;
}

/** 可绑定属性：写字面量，或写绑定去引用 data 里的值。 */
export type UIBindable<T> = T | UIBinding;

/** 动作上下文项：把面板里改过的值随动作带回后端。 */
export interface UIActionContextItem {
  key: string;
  value: unknown;
}

/**
 * 面板动作。**内部统一形态**：`{name, context?}`。
 *
 * A2UI v0.9.1 的消息里它是 envelope 形态 `{"event": {"name", "context"}}`
 * （`ui/versions/v0_9_1.py` 负责翻译），解析层会把两种形态归一成这个。
 */
export interface UIAction {
  name: string;
  context?: UIActionContextItem[];
}

// ---------------------------------------------------------------------------
// 组件属性（映射表 → 自动生成判别联合）
// ---------------------------------------------------------------------------

export interface UITableColumn {
  key: string;
  title: string;
  width?: number;
}

export interface UISelectOption {
  value: string;
  label: string;
}

export interface UIChoiceOption extends UISelectOption {
  desc?: string;
}

export interface UIStepItem {
  label: string;
  status: UIStepStatus;
}

/**
 * ECharts option（与 `generate_chart` 的产物同形态）。
 *
 * 刻意用 `Record<string, unknown>` 而不是抄一份 ECharts 类型定义：抄一份
 * 等于给自己埋一个「ECharts 升版就腐化」的第二真源。配色由前端主题决定，
 * 后端已在 normalized 阶段剥掉顶层展示性键（044 §9.4）。
 */
export type UIChartOption = Record<string, unknown>;

/** FileList 的文件项（无 download_url：IR 里只有工作区相对路径）。 */
export interface UIFileItem {
  name: string;
  /** 工作区内相对路径（禁绝对路径与 `..`，后端已硬拒）。 */
  path?: string;
  /** 字节数。 */
  size?: number;
}

/**
 * 组件名 → 属性表。**增删组件只改这一处**，`UIComponent` 联合类型与运行时
 * 白名单 `COMPONENT_PROPS` 都从这里派生（后者手写以保证运行时可读）。
 */
export interface UIComponentPropsMap {
  // A 组 · 布局
  Column: { children: string[]; gap?: UIGap; align?: UIAlign; justify?: UIJustify };
  Row: { children: string[]; gap?: UIGap; align?: UIAlign; wrap?: boolean };
  Card: { child: string; title?: UIBindable<string>; tone?: UITone };
  Divider: { orientation?: UIOrientation };
  // B 组 · 展示
  Text: { text: UIBindable<string>; variant?: UITextVariant; tone?: UITone };
  Badge: { text: UIBindable<string>; tone?: UITone };
  Image: { url: string; alt?: string; aspectRatio?: number; caption?: UIBindable<string> };
  Table: {
    columns: UITableColumn[];
    rows: UIBindable<Record<string, unknown>[]>;
    maxHeight?: number;
    caption?: UIBindable<string>;
  };
  Progress: { value: UIBindable<number>; label?: UIBindable<string>; tone?: UITone };
  Steps: { items: UIStepItem[]; caption?: UIBindable<string> };
  // C 组 · 输入
  TextField: {
    label: string;
    value: UIBindable<string>;
    placeholder?: string;
    required?: boolean;
  };
  TextArea: { label: string; value: UIBindable<string>; rows?: number };
  NumberField: {
    label: string;
    value: UIBindable<number>;
    min?: number;
    max?: number;
    step?: number;
    unit?: string;
  };
  Select: { label: string; value: UIBindable<string>; options: UISelectOption[] };
  ChoicePicker: {
    value: UIBindable<string>;
    options: UIChoiceOption[];
    multiple?: boolean;
  };
  Checkbox: { label: string; checked: UIBindable<boolean> };
  Switch: { label: string; checked: UIBindable<boolean> };
  // D 组 · 动作
  Button: {
    text: UIBindable<string>;
    variant?: UIButtonVariant;
    disabled?: boolean;
    action: UIAction;
  };
  // E 组 · 富媒体（S5）
  // 三个组件**只做 props 转发**：Chart 交给 ChartBlock、Graph 交给 GraphBlock、
  // FileList 复用 ToolFileList 的行样式。**禁止第二套 ECharts/X6 代码**。
  Chart: { option: UIChartOption; height?: number; caption?: UIBindable<string> };
  Graph: { ir: GraphIR; height?: number; caption?: UIBindable<string> };
  FileList: { files: UIFileItem[]; caption?: UIBindable<string> };
}

export type UIComponentName = keyof UIComponentPropsMap;

/** 判别联合：`switch (c.component)` 可精确窄化到对应属性类型。 */
export type UIComponent = {
  [K in UIComponentName]: { id: string; component: K } & UIComponentPropsMap[K];
}[UIComponentName];

/** 取某个组件名的具体类型（registry 用）。 */
export type ExtractUIComponent<K extends UIComponentName> = Extract<UIComponent, { component: K }>;

// ---------------------------------------------------------------------------
// 运行时白名单（必须与上面的类型表保持一致）
// ---------------------------------------------------------------------------

/**
 * 每个组件允许的**属性白名单**（不含 `id` / `component` 两个结构键）。
 * 解析时逐键裁剪：不在表里的键直接丢弃（纵深防御，防脏键进渲染层）。
 */
export const COMPONENT_PROPS: Record<UIComponentName, readonly string[]> = {
  Column: ["children", "gap", "align", "justify"],
  Row: ["children", "gap", "align", "wrap"],
  Card: ["child", "title", "tone"],
  Divider: ["orientation"],
  Text: ["text", "variant", "tone"],
  Badge: ["text", "tone"],
  Image: ["url", "alt", "aspectRatio", "caption"],
  Table: ["columns", "rows", "maxHeight", "caption"],
  Progress: ["value", "label", "tone"],
  Steps: ["items", "caption"],
  TextField: ["label", "value", "placeholder", "required"],
  TextArea: ["label", "value", "rows"],
  NumberField: ["label", "value", "min", "max", "step", "unit"],
  Select: ["label", "value", "options"],
  ChoicePicker: ["value", "options", "multiple"],
  Checkbox: ["label", "checked"],
  Switch: ["label", "checked"],
  Button: ["text", "variant", "disabled", "action"],
  Chart: ["option", "height", "caption"],
  Graph: ["ir", "height", "caption"],
  FileList: ["files", "caption"],
};

export const COMPONENT_NAMES: readonly UIComponentName[] = Object.keys(
  COMPONENT_PROPS,
) as UIComponentName[];

export const COMPONENT_NAMES_SET: ReadonlySet<string> = new Set<string>(COMPONENT_NAMES);

/** 分组展示（用于调试与文档，渲染不需要）。 */
export const COMPONENT_GROUPS: Record<string, readonly UIComponentName[]> = {
  layout: ["Column", "Row", "Card", "Divider"],
  display: ["Text", "Badge", "Image", "Table", "Progress", "Steps"],
  input: ["TextField", "TextArea", "NumberField", "Select", "ChoicePicker", "Checkbox", "Switch"],
  action: ["Button"],
  media: ["Chart", "Graph", "FileList"],
};

/**
 * 结构键：`id` / `component` 之外的键都必须在 `COMPONENT_PROPS[name]` 里。
 */
export const STRUCTURAL_KEYS: readonly string[] = ["id", "component"];

/** 内置动作（对齐 catalog.py `BUILTIN_ACTIONS`），任何面板可直接用。 */
export const BUILTIN_ACTIONS: readonly string[] = [
  "submit",
  "cancel",
  "refresh",
  "dismiss",
  "open",
];

// ---------------------------------------------------------------------------
// 限额（对齐 catalog.py，前端二次裁剪）
// ---------------------------------------------------------------------------

export const MAX_COMPONENTS = 120;
export const MAX_DEPTH = 12;
export const MAX_TABLE_ROWS = 200;
export const MAX_ACTIONS = 8;
/** 重组件（Chart + Graph）同屏合计上限。 */
export const MAX_RICH_MEDIA = 2;
/** 单类重组件上限（各 1 个）：Chart 与 Graph 都属高成本项。 */
export const MAX_CHART = 1;
export const MAX_GRAPH = 1;
/** FileList 条目上限。 */
export const MAX_FILE_ITEMS = 50;
/** Chart.option 序列化后的字符上限（对齐后端，只兜底病态 payload）。 */
export const MAX_CHART_OPTION_CHARS = 40_000;

/** 需要计入「重组件」限额的组件名。 */
export const RICH_MEDIA_COMPONENTS: ReadonlySet<string> = new Set(["Chart", "Graph"]);

// ---------------------------------------------------------------------------
// 归一化后的面板（渲染层的数据形状）
// ---------------------------------------------------------------------------

/** 面板标题长度上限（超出由解析层截断，不报错）。 */
export const MAX_TITLE_LENGTH = 40;

/**
 * 前端归一化后的面板。`components` 是**邻接表 map**（IR 里是扁平数组），
 * 渲染从 `rootId` 递归；`dataModel` 由 `UISurfaceBlock` 持有为 React state。
 */
export interface UISurface {
  surfaceId: string;
  /** 同一 surfaceId 内的单调序号，用于乱序丢弃。 */
  seq: number;
  catalogId?: string;
  title?: string;
  components: Record<string, UIComponent>;
  rootId: string;
  dataModel: Record<string, unknown>;
  /** 本面板登记的业务动作（内置动作不在其中）。 */
  actions: string[];
  status: UISurfaceStatus;
  /** 乐观提交态：正在进行的 action_id。 */
  pendingActionId?: string | null;
  /** 面板所属的 assistant 消息（动作回填需要定位）。 */
  messageId?: string;
}

/** 面板渲染上下文：组件通过它读数据、写数据、触发动作、递归渲染子组件。 */
export interface SurfaceContext {
  data: Record<string, unknown>;
  /** 写回数据模型（不可变更新，触发重渲染）。 */
  setValue: (path: string, value: unknown) => void;
  /**
   * 触发动作（收集 context + 当前 dataModel 提交给后端）。
   *
   * `label` 是触发它的控件文案（按钮文本）。后端要把它作为**可见 user 消息
   * 正文**的主体（044 §8.2：`message_parts` 不进模型上下文，动作必须落进正文），
   * 而动作本身不带文案——同一个 action 可以由多个按钮触发，label 属于控件。
   */
  submit: (action: UIAction, componentId: string, label?: string) => void;
  /** 面板状态：closed 时输入控件只读、按钮禁用。 */
  status: UISurfaceStatus;
  pendingActionId?: string | null;
  /** 求值绑定：`{path}` 取 data 值，字面量原样返回。 */
  resolve: <T>(value: UIBindable<T> | undefined) => T | undefined;
  /** 按 id 递归渲染子组件（容器类组件用）。 */
  renderChild: (id: string) => ReactNode;
  /**
   * 当前会话工作区路径。只服务富媒体组件（Chart/Graph 的导出按钮、
   * FileList 的「打开所在目录」），组件自身不读文件 —— 044 §16.5
   * 明令渲染期禁同步 IPC / 读文件，这里只做异步动作的路径参数。
   */
  workspacePath?: string | null;
}

/** 每个渲染组件的 props（registry 用）。 */
export interface CompProps<K extends UIComponentName> {
  component: ExtractUIComponent<K>;
  ctx: SurfaceContext;
}

/** 解析结果：失败给原因，**不抛**（调用方降级为一行提示）。 */
export type UISurfaceParseResult = { ok: true; surface: UISurface } | { ok: false; reason: string };
