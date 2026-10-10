/**
 * 面板解析与归一化（纵深防御 L3）。
 *
 * 设计文档：`docs/design/028-a2ui-integration-20261009.md` §5.1 / §9.1。
 *
 * 三件事，缺一不可：
 * 1. **逐组件白名单裁剪** —— 只留下 `COMPONENT_PROPS` 声明的键；
 * 2. **禁用键剔除** —— `on*` / `style` / `className` / `__proto__` /
 *    `dangerouslySetInnerHTML`（防 XSS 与原型污染），**递归**检查；
 *    **例外**：透传给第三方渲染器的数据字段（Chart.option / Graph.ir，
 *    见 `OPAQUE_PROP_KEYS`）只拦原型污染键 —— `on*` 在 ECharts option 里
 *    是合法字段（`series.onZero` 正撞规则），按组件属性层规则扫会误拒合法图表；
 * 3. **引用完整性与结构校验** —— 未知组件 / 缺引用 / 环 / 深度 / 限额。
 *
 * 核心约定：**非法就返回 `{ok:false}`，绝不抛、绝不"尽力渲染"** ——
 * 半张错误的面板比一行明确的失败提示更糟（照 `GraphIR.ts` 的范式）。
 *
 * 两个入口共用同一个归一化内核：
 * - `parseA2UIFrame` —— 主路径，解析 `event: a2ui` 的 v0.9.1 消息帧；
 * - `parseUISurfaceIR` —— 兜底路径（`tool` 事件的 `data.uiSurface`）
 *   与历史回放（`ui_surface` part），吃后端的**中立 IR**。
 */

import {
  BUILTIN_ACTIONS,
  COMPONENT_NAMES_SET,
  COMPONENT_PROPS,
  MAX_ACTIONS,
  MAX_CHART,
  MAX_CHART_OPTION_CHARS,
  MAX_COMPONENTS,
  MAX_DEPTH,
  MAX_FILE_ITEMS,
  MAX_GRAPH,
  MAX_RICH_MEDIA,
  MAX_TABLE_ROWS,
  MAX_TITLE_LENGTH,
  RICH_MEDIA_COMPONENTS,
  type UIComponent,
  type UIComponentName,
  type UISurface,
  type UISurfaceParseResult,
  type UISurfaceStatus,
} from "./types";
import { getByPath, isBinding } from "./dataModel";
import { parseGraphIR } from "@/pages/chat/components/GraphBlock/GraphIR";

/** 中立 IR 顶层允许的字段（对齐 catalog.py `SURFACE_TOP_KEYS`）。 */
const IR_TOP_KEYS: readonly string[] = ["surfaceId", "title", "components", "data", "actions"];

/** 业务动作名模式（对齐 catalog.py `ACTION_NAME_PATTERN`）。 */
const ACTION_NAME_PATTERN = /^[a-z][a-z0-9_]{0,31}$/;

/**
 * 各组件**必需**属性（对齐 catalog.py 的 `required=True`）。
 * 后端已硬拒缺失，这里是防版本漂移的兜底。
 */
const REQUIRED_PROPS: Record<UIComponentName, readonly string[]> = {
  Column: ["children"],
  Row: ["children"],
  Card: ["child"],
  Divider: [],
  Text: ["text"],
  Badge: ["text"],
  Image: ["url"],
  Table: ["columns", "rows"],
  Progress: ["value"],
  Steps: ["items"],
  TextField: ["label", "value"],
  TextArea: ["label", "value"],
  NumberField: ["label", "value"],
  Select: ["label", "value", "options"],
  ChoicePicker: ["value", "options"],
  Checkbox: ["label", "checked"],
  Switch: ["label", "checked"],
  Button: ["text", "action"],
  Chart: ["option"],
  Graph: ["ir"],
  FileList: ["files"],
};

/**
 * **透传给第三方渲染器的数据字段**（Chart 的 ECharts option、Graph 的 GraphIR）。
 *
 * 这些字段里没有一个是 DOM 属性，`on*` 这种名字在那里是合法业务字段
 * ——ECharts 的 `series.onZero` 正撞 `^on[A-Z]` 规则，若按组件属性层同样
 * 规则扫，合法图表会被误拒。因此只对它们拦**原型污染键**。
 */
const OPAQUE_PROP_KEYS: Record<string, readonly string[]> = {
  Chart: ["option"],
  Graph: ["ir"],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 原型污染键：**任何深度**都要拦（含透传数据内部）。 */
function isProtoKey(key: string): boolean {
  return key === "__proto__" || key === "constructor" || key === "prototype";
}

/** 值型危险键：事件处理 / 内联样式 / 类名 / HTML 注入。只在组件属性层拦。 */
function isValueKey(key: string): boolean {
  if (key === "style" || key === "className" || key === "dangerouslySetInnerHTML") {
    return true;
  }
  return /^on[A-Z]/.test(key);
}

/** 只查原型污染键（用于 `OPAQUE_PROP_KEYS` 子树）。 */
function findProtoOnly(value: unknown, path: string): string | null {
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i += 1) {
      const hit = findProtoOnly(value[i], `${path}[${i}]`);
      if (hit) return hit;
    }
    return null;
  }
  if (!isRecord(value)) return null;
  for (const key of Object.keys(value)) {
    if (isProtoKey(key)) return `${path}.${key} 是禁用字段`;
    const hit = findProtoOnly(value[key], `${path}.${key}`);
    if (hit) return hit;
  }
  return null;
}

/**
 * 递归查找危险键，返回首个命中的路径（用于报错定位）。
 *
 * `opaqueKeys` 命中的子树只拦原型污染键——见 `OPAQUE_PROP_KEYS` 的说明。
 */
function findForbidden(
  value: unknown,
  path: string,
  opaqueKeys: readonly string[] = [],
): string | null {
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i += 1) {
      const hit = findForbidden(value[i], `${path}[${i}]`, opaqueKeys);
      if (hit) return hit;
    }
    return null;
  }
  if (!isRecord(value)) return null;
  for (const key of Object.keys(value)) {
    if (isProtoKey(key)) return `${path}.${key} 是禁用字段`;
    const child = value[key];
    if (opaqueKeys.includes(key)) {
      const hit = findProtoOnly(child, `${path}.${key}`);
      if (hit) return hit;
      continue;
    }
    if (isValueKey(key)) return `${path}.${key} 是禁用字段`;
    const hit = findForbidden(child, `${path}.${key}`, opaqueKeys);
    if (hit) return hit;
  }
  return null;
}

/** 确认字符串数组（children）。 */
function asIdList(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  if (!value.every((item): item is string => typeof item === "string" && item.length > 0)) {
    return null;
  }
  return value;
}

/**
 * 图片 URL 安全判定：仅 http(s) 或工作区相对路径。
 * 拒绝绝对路径 / 上跳 / 协议相对 / `file:` / `data:` / `javascript:`。
 */
export function isSafeImageUrl(raw: unknown): boolean {
  if (typeof raw !== "string") return false;
  const url = raw.trim();
  if (!url) return false;
  if (/^https?:\/\//i.test(url)) return true;
  if (url.startsWith("//")) return false;
  if (url.startsWith("/")) return false;
  if (/^[a-z][a-z0-9+.-]*:/i.test(url)) return false;
  if (url.split("/").includes("..") || url.split("\\").includes("..")) return false;
  return true;
}

/** 归一化动作：兼容 IR 形态 `{name, context}` 与 v0.9.1 envelope `{event:{name,context}}`。 */
function normalizeAction(raw: unknown): { name: string; context?: unknown[] } | null {
  if (!isRecord(raw)) return null;
  const envelope = raw.event;
  const source: Record<string, unknown> = isRecord(envelope) ? envelope : raw;
  const name = source.name;
  if (typeof name !== "string" || !name) return null;
  const context = Array.isArray(source.context)
    ? source.context.filter(
        (item) => isRecord(item) && typeof (item as { key?: unknown }).key === "string",
      )
    : undefined;
  return context ? { name, context } : { name };
}

/**
 * 判断动作是否被允许。
 *
 * `strict=true`（中立 IR 路径）：业务动作**必须在 `actions` 里登记**——
 * 后端 validator 已硬拒未登记者，这里是纵深防御。
 * `strict=false`（A2UI 消息路径）：协议层没有登记表（`createSurface` 不带
 * `actions`），只校验名字合法性，避免把合法面板误判为非法。
 */
function isAllowedAction(name: string, registered: ReadonlySet<string>, strict: boolean): boolean {
  if (BUILTIN_ACTIONS.includes(name)) return true;
  if (!ACTION_NAME_PATTERN.test(name)) return false;
  return strict ? registered.has(name) : true;
}

interface NormalizeInput {
  surfaceId: string;
  seq: number;
  catalogId?: string;
  title?: unknown;
  rawComponents: unknown;
  dataModel?: unknown;
  registeredActions?: unknown;
  status: UISurfaceStatus;
  messageId?: string;
  /** true=要求业务动作已在 `actions` 登记（IR 路径）；false=只校验名字（消息路径）。 */
  strictActions: boolean;
}

/**
 * 归一化内核：裁剪 + 校验 + 建 map。
 *
 * 可达性规则：从 `root` 出发遍历，只保留可达组件（不可达的静默丢弃 —— 后端
 * 已保证全部可达，这里防脏数据）。因此"组件数上限"按**可达数**计。
 */
function normalizeSurface(input: NormalizeInput): UISurfaceParseResult {
  const { surfaceId, seq, status, messageId } = input;
  if (!surfaceId) return { ok: false, reason: "面板缺少 surfaceId" };

  // 1) 注册动作表（业务动作白名单）
  const registered = new Set<string>();
  if (Array.isArray(input.registeredActions)) {
    for (const item of input.registeredActions) {
      if (typeof item === "string" && item) registered.add(item);
    }
  }
  if (registered.size > MAX_ACTIONS) {
    return { ok: false, reason: `登记动作数 ${registered.size} 超过上限 ${MAX_ACTIONS}` };
  }

  // 2) 组件数组 → 逐项裁剪
  const rawList = input.rawComponents;
  if (!Array.isArray(rawList) || rawList.length === 0) {
    return { ok: false, reason: "components 为空" };
  }
  if (rawList.length > MAX_COMPONENTS) {
    return {
      ok: false,
      reason: `组件数 ${rawList.length} 超过上限 ${MAX_COMPONENTS}`,
    };
  }

  const dataModel = isRecord(input.dataModel) ? input.dataModel : {};
  const components: Record<string, UIComponent> = {};

  for (let index = 0; index < rawList.length; index += 1) {
    const item = rawList[index];
    if (!isRecord(item)) return { ok: false, reason: `components[${index}] 不是对象` };

    // 透传数据字段（Chart.option / Graph.ir）只拦原型污染键，见 OPAQUE_PROP_KEYS。
    const declared = typeof item.component === "string" ? item.component : "";
    const forbidden = findForbidden(item, `components[${index}]`, OPAQUE_PROP_KEYS[declared] ?? []);
    if (forbidden) return { ok: false, reason: forbidden };

    const id = item.id;
    if (typeof id !== "string" || !id) {
      return { ok: false, reason: `components[${index}].id 缺失` };
    }
    if (components[id]) return { ok: false, reason: `组件 id 重复：${id}` };

    const name = item.component;
    if (typeof name !== "string" || !COMPONENT_NAMES_SET.has(name)) {
      return {
        ok: false,
        reason: `components[${index}] 未知组件 ${String(name)}（允许：${[...COMPONENT_NAMES_SET].join("/")}）`,
      };
    }
    const compName = name as UIComponentName;

    // 逐键白名单裁剪：只保留声明过的属性
    const picked: Record<string, unknown> = { id, component: compName };
    for (const key of COMPONENT_PROPS[compName]) {
      if (key in item) picked[key] = item[key];
    }
    // 结构键不得混入属性表之外的东西（已由裁剪保证）

    // 必需属性
    for (const key of REQUIRED_PROPS[compName]) {
      if (picked[key] === undefined) {
        return { ok: false, reason: `组件 ${id}（${compName}）缺少必需属性 ${key}` };
      }
    }

    // 引用型属性的类型校验
    if (compName === "Column" || compName === "Row") {
      if (asIdList(picked.children) === null) {
        return { ok: false, reason: `组件 ${id}（${compName}）的 children 必须是 id 数组` };
      }
    }
    if (compName === "Card") {
      if (typeof picked.child !== "string" || !picked.child) {
        return { ok: false, reason: `组件 ${id}（Card）的 child 必须是单个 id` };
      }
    }

    // 图片 URL 安全
    if (compName === "Image" && !isSafeImageUrl(picked.url)) {
      return {
        ok: false,
        reason: `组件 ${id}（Image）的 url 不安全：仅允许 http(s) 或工作区相对路径`,
      };
    }

    // Table 行数（绑定先求值）
    if (compName === "Table") {
      const rowsRaw = picked.rows;
      const rows = isBinding(rowsRaw) ? getByPath(dataModel, rowsRaw.path) : rowsRaw;
      if (!Array.isArray(rows)) {
        return { ok: false, reason: `组件 ${id}（Table）的 rows 求值后不是数组` };
      }
      if (rows.length > MAX_TABLE_ROWS) {
        return {
          ok: false,
          reason: `组件 ${id}（Table）行数 ${rows.length} 超过上限 ${MAX_TABLE_ROWS}`,
        };
      }
      if (!Array.isArray(picked.columns) || picked.columns.length === 0) {
        return { ok: false, reason: `组件 ${id}（Table）的 columns 不能为空` };
      }
    }

    // Button 动作
    if (compName === "Button") {
      const action = normalizeAction(picked.action);
      if (!action) return { ok: false, reason: `组件 ${id}（Button）缺少合法的 action.name` };
      if (!isAllowedAction(action.name, registered, input.strictActions)) {
        return {
          ok: false,
          reason: `组件 ${id} 引用了未登记的动作 ${action.name}（需在 actions 里声明，或用内置动作 ${BUILTIN_ACTIONS.join("/")}）`,
        };
      }
      picked.action = action;
    }

    // Chart.option：只校验「非空对象 + 体积」，不校验 ECharts schema
    // （抄一份 ECharts 类型定义 = 第二个会腐化的真源；非法 option 的表现是
    // 空图，不会把页面打崩）。
    if (compName === "Chart") {
      if (!isRecord(picked.option) || Object.keys(picked.option).length === 0) {
        return {
          ok: false,
          reason: `组件 ${id}（Chart）的 option 必须是非空 ECharts option 对象`,
        };
      }
      // 序列化失败（循环引用等）直接判非法：给不出体积就没法守上限。
      const optionJson = (() => {
        try {
          return JSON.stringify(picked.option);
        } catch {
          return null;
        }
      })();
      if (optionJson === null) {
        return { ok: false, reason: `组件 ${id}（Chart）的 option 含有无法序列化的值` };
      }
      if (optionJson.length > MAX_CHART_OPTION_CHARS) {
        return {
          ok: false,
          reason: `组件 ${id}（Chart）的 option 约 ${optionJson.length} 字符，超过上限 ${MAX_CHART_OPTION_CHARS}`,
        };
      }
    }

    // Graph.ir：**复用 GraphBlock 的 parseGraphIR**，不写第二份规则
    //（否则会出现「render_graph 通过、塞进面板却渲染不出来」的割裂）。
    if (compName === "Graph") {
      const parsed = parseGraphIR(picked.ir);
      if (!parsed.ok) {
        return { ok: false, reason: `组件 ${id}（Graph）的 ir 不是合法 GraphIR：${parsed.reason}` };
      }
      picked.ir = parsed.ir;
    }

    // FileList.files：非空、限量、逐项必须有 name、path 必须是工作区相对路径。
    if (compName === "FileList") {
      const files = picked.files;
      if (!Array.isArray(files) || files.length === 0) {
        return { ok: false, reason: `组件 ${id}（FileList）的 files 必须是非空数组` };
      }
      if (files.length > MAX_FILE_ITEMS) {
        return {
          ok: false,
          reason: `组件 ${id}（FileList）有 ${files.length} 项，超过上限 ${MAX_FILE_ITEMS}`,
        };
      }
      for (const file of files) {
        if (!isRecord(file) || typeof file.name !== "string" || !file.name.trim()) {
          return { ok: false, reason: `组件 ${id}（FileList）的每一项都必须有 name` };
        }
        const filePath = file.path;
        if (typeof filePath === "string" && filePath) {
          if (filePath.startsWith("/") || filePath.split("/").includes("..")) {
            return {
              ok: false,
              reason: `组件 ${id}（FileList）的 path 必须是工作区相对路径（禁绝对路径与 ..）`,
            };
          }
        }
      }
    }

    components[id] = picked as unknown as UIComponent;
  }

  // 富媒体限额：Chart/Graph 合计 ≤ MAX_RICH_MEDIA 且同类各 ≤ 1（后端已硬拒，
  // 这里是防版本漂移；重组件会显著拖慢滚动，044 §16.2）。
  const heavy = Object.values(components).filter((comp) =>
    RICH_MEDIA_COMPONENTS.has(comp.component),
  );
  if (heavy.length > MAX_RICH_MEDIA) {
    return {
      ok: false,
      reason: `重组件（Chart/Graph）共 ${heavy.length} 个，超过上限 ${MAX_RICH_MEDIA}`,
    };
  }
  for (const [kind, limit] of [
    ["Chart", MAX_CHART],
    ["Graph", MAX_GRAPH],
  ] as const) {
    const count = heavy.filter((comp) => comp.component === kind).length;
    if (count > limit) {
      return { ok: false, reason: `${kind} 组件 ${count} 个，超过上限 ${limit}` };
    }
  }

  // 3) 结构校验：root 必须存在；从 root 遍历（引用完整性 + 环 + 深度 + 可达数）
  if (!components.root) return { ok: false, reason: "缺少 id 为 root 的根组件" };

  const reachable = new Set<string>();
  const stack: Array<{ id: string; depth: number }> = [{ id: "root", depth: 1 }];
  while (stack.length) {
    const { id, depth } = stack.pop() as { id: string; depth: number };
    if (reachable.has(id)) continue;
    reachable.add(id);
    if (reachable.size > MAX_COMPONENTS) {
      return { ok: false, reason: `可达组件数超过上限 ${MAX_COMPONENTS}` };
    }
    if (depth > MAX_DEPTH) {
      return { ok: false, reason: `嵌套深度超过上限 ${MAX_DEPTH}（在 ${id} 处）` };
    }
    const comp = components[id];
    if (!comp) continue; // 引用不存在的 id：下面单独报
    const childIds =
      comp.component === "Column" || comp.component === "Row"
        ? comp.children
        : comp.component === "Card"
          ? [comp.child]
          : [];
    for (const childId of childIds) {
      if (!components[childId]) {
        return { ok: false, reason: `组件 ${id} 引用了不存在的组件 ${childId}` };
      }
      stack.push({ id: childId, depth: depth + 1 });
    }
  }

  // 4) 收敛：只保留可达组件（不可达的丢弃）
  const finalComponents: Record<string, UIComponent> = {};
  for (const id of reachable) finalComponents[id] = components[id];

  const title =
    typeof input.title === "string" && input.title.trim()
      ? input.title.trim().slice(0, MAX_TITLE_LENGTH)
      : undefined;

  return {
    ok: true,
    surface: {
      surfaceId,
      seq,
      catalogId: input.catalogId,
      title,
      components: finalComponents,
      rootId: "root",
      dataModel,
      actions: [...registered],
      status,
      pendingActionId: null,
      messageId,
    },
  };
}

interface ParseOptions {
  seq?: number;
  messageId?: string;
  status?: UISurfaceStatus;
}

/**
 * 主路径：解析 `event: a2ui` 的一帧 v0.9.1 消息。
 *
 * 帧内消息顺序固定为 `createSurface` → `updateComponents` → `updateDataModel?`；
 * `deleteSurface` 单独返回，交调用方收起面板。
 */
export function parseA2UIFrame(
  payload: unknown,
  options: ParseOptions = {},
):
  | { ok: true; surface: UISurface }
  | { ok: false; reason: string }
  | { deleted: true; surfaceId: string } {
  if (!isRecord(payload)) return { ok: false, reason: "a2ui 事件载荷不是对象" };
  const messages = payload.messages;
  if (!Array.isArray(messages) || messages.length === 0) {
    return { ok: false, reason: "a2ui 帧内没有消息" };
  }

  let surfaceId = typeof payload.surfaceId === "string" ? payload.surfaceId : "";
  let catalogId: string | undefined;
  let rawComponents: unknown;
  let dataModel: unknown;
  // 标题与 surfaceId/seq 一样走**帧封装顶层**，不在 messages 里
  //（`createSurface` 是 A2UI 协议消息，后端有意没往里塞自定义字段）。
  // 漏读这一行会让面板标题恒为 undefined —— 除标题外一切正常，很难察觉。
  const title: unknown = typeof payload.title === "string" ? payload.title : undefined;

  for (const message of messages) {
    if (!isRecord(message)) continue;
    if (isRecord(message.createSurface)) {
      const create = message.createSurface;
      if (typeof create.surfaceId === "string") surfaceId = create.surfaceId;
      if (typeof create.catalogId === "string") catalogId = create.catalogId;
    } else if (isRecord(message.updateComponents)) {
      rawComponents = message.updateComponents.components;
    } else if (isRecord(message.updateDataModel)) {
      dataModel = message.updateDataModel.value;
    } else if (isRecord(message.deleteSurface)) {
      const id = message.deleteSurface.surfaceId;
      return { deleted: true, surfaceId: typeof id === "string" ? id : surfaceId };
    }
  }

  return normalizeSurface({
    surfaceId,
    seq: typeof payload.seq === "number" ? payload.seq : (options.seq ?? 0),
    catalogId,
    title,
    rawComponents,
    dataModel,
    registeredActions: undefined,
    status: options.status ?? "live",
    messageId: options.messageId,
    // 协议层没有 actions 登记表：只校验动作名合法性，不要求已登记。
    strictActions: false,
  });
}

/**
 * 兜底 / 回放路径：解析后端的**中立 IR**
 * （`tool` 事件的 `data.uiSurface`，或历史 `ui_surface` part）。
 */
export function parseUISurfaceIR(raw: unknown, options: ParseOptions = {}): UISurfaceParseResult {
  if (!isRecord(raw)) return { ok: false, reason: "面板 IR 不是对象" };
  const unknownTop = findUnknownTopKey(raw);
  if (unknownTop) return { ok: false, reason: `面板 IR 含未知顶层字段：${unknownTop}` };
  if (!Array.isArray(raw.components) || raw.components.length === 0) {
    return { ok: false, reason: "面板 IR 没有组件" };
  }
  return normalizeSurface({
    surfaceId: typeof raw.surfaceId === "string" ? raw.surfaceId : "",
    seq: typeof options.seq === "number" ? options.seq : 0,
    title: raw.title,
    rawComponents: raw.components,
    dataModel: raw.data,
    registeredActions: raw.actions,
    status: options.status ?? "live",
    messageId: options.messageId,
    // 中立 IR 带 actions 登记表：业务动作必须在其中（后端已硬拒，兜底）。
    strictActions: true,
  });
}

/** 找出 IR 里第一个未知顶层字段（只做诊断，返回字段名）。 */
function findUnknownTopKey(raw: Record<string, unknown>): string | null {
  for (const key of Object.keys(raw)) {
    if (!IR_TOP_KEYS.includes(key)) return key;
  }
  return null;
}
