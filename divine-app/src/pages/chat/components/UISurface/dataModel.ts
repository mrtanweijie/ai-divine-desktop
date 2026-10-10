/**
 * 面板数据模型：RFC 6901 JSON Pointer 子集的取值 / 写值。
 *
 * 设计文档：`docs/design/028-a2ui-integration-20261009.md` §4.2 / §5.2。
 *
 * 只支持绑定形式 `{"path": "/a/b"}`（`catalog.py` 的 `BINDING_KEY`）。
 * 写值一律**不可变更新**（返回新对象），因为 `dataModel` 是
 * `UISurfaceBlock` 的 React state，原地改会让重渲染失效。
 */

import type { UIBindable, UIBinding, UISurface } from "./types";

/** 判定一个属性值是不是数据绑定 `{"path": "..."}`。 */
export function isBinding(value: unknown): value is UIBinding {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    typeof (value as { path?: unknown }).path === "string"
  );
}

/**
 * 把 JSON Pointer 拆成段。空串与 `/` 都表示**根**。
 *
 * 转义规则（RFC 6901）：先解 `~1` → `/`，再解 `~0` → `~`（顺序不可反，
 * 否则 `~01` 会被错误解成 `/`）。
 */
export function parsePointer(path: string): string[] {
  if (!path || path === "/") return [];
  if (!path.startsWith("/")) return [];
  return path
    .slice(1)
    .split("/")
    .map((segment) => segment.replace(/~1/g, "/").replace(/~0/g, "~"));
}

/** 按指针取值；路径不存在返回 `undefined`（不抛）。 */
export function getByPath(data: unknown, path: string): unknown {
  const segments = parsePointer(path);
  let current: unknown = data;
  for (const segment of segments) {
    if (current == null || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
}

function setDeep(node: unknown, segments: string[], index: number, value: unknown): unknown {
  const segment = segments[index];
  const isArray = Array.isArray(node);
  const container: Record<string, unknown> = isArray
    ? ([...(node as unknown[])] as unknown as Record<string, unknown>)
    : { ...((node as Record<string, unknown> | null) ?? {}) };
  if (index === segments.length - 1) {
    container[segment] = value;
    return container;
  }
  const child = (node as Record<string, unknown> | null)?.[segment];
  container[segment] = setDeep(child, segments, index + 1, value);
  return container;
}

/**
 * 不可变写值。返回**新对象**（调用方负责 setState）。
 *
 * 中间层不存在时会逐级补空对象 —— 后端 validator 已保证绑定路径存在，
 * 这里是防御性补齐（热更新旧面板时可能出现路径被 `updateDataModel` 换掉）。
 */
export function setByPath(
  data: Record<string, unknown>,
  path: string,
  value: unknown,
): Record<string, unknown> {
  const segments = parsePointer(path);
  if (segments.length === 0) {
    return value && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : data;
  }
  return setDeep(data, segments, 0, value) as Record<string, unknown>;
}

/** 求值一个可绑定属性：绑定取 `data` 里的值，字面量原样返回。 */
export function resolveBindable<T>(
  data: Record<string, unknown>,
  value: UIBindable<T> | undefined,
): T | undefined {
  if (value === undefined || value === null) return undefined;
  if (isBinding(value)) return getByPath(data, value.path) as T | undefined;
  return value as T;
}

// ---------------------------------------------------------------------------
// 输入控件的当前值（动作回填的兜底来源）
// ---------------------------------------------------------------------------

/**
 * 输入控件的「值属性」：这些控件的当前值就是用户填的参数。
 *
 * 与 `registry.tsx` 的 `useBoundValue` / `bindingPath` 一一对应 —— 改输入
 * 组件的绑定属性时**这张表要一起改**（别让它像 `MessageHelpers` 的双映射表
 * 那样悄悄漂移）。
 */
const INPUT_BINDING_PROPS: Record<string, "value" | "checked"> = {
  TextField: "value",
  TextArea: "value",
  NumberField: "value",
  Select: "value",
  ChoicePicker: "value",
  Checkbox: "checked",
  Switch: "checked",
};

export interface UIInputBinding {
  /** 绑定路径（RFC 6901，如 `/labor_input`）。 */
  path: string;
  /** 回传给后端的字段名：路径末段（撞名时退回完整路径）。 */
  key: string;
}

/**
 * 收集面板里**所有输入控件的绑定路径**（去重、稳定顺序）。
 *
 * **这是「动作上下文」的兜底来源**：模型经常只写 `action.name` 而漏掉
 * `action.context`（2026-10-10 实际生成的 `cost_dashboard_v2` 就是这样，
 * 三个 NumberField 都绑了 data 路径，但 `Button.action` 只有一个 `name`），
 * 于是用户点了「提交参数」，面板上的数字**静默丢失** —— 后端只收到动作名，
 * 因为 `_surface_action_question` 只认 `context`，而 `data_model` 里的值
 * 没人往正文里搬。
 *
 * 修法选在**前端兜底**而不是「要求模型别忘」：兜底是数据驱动的（直接从 IR
 * 推导），对**已经存在的老面板**同样生效（它们的 IR 里本来就有输入控件），
 * 而改提示词只能影响之后生成的面板。
 */
export function collectInputBindings(surface: UISurface): UIInputBinding[] {
  const out: UIInputBinding[] = [];
  const seenPaths = new Set<string>();
  const seenKeys = new Set<string>();
  for (const component of Object.values(surface.components)) {
    const prop = INPUT_BINDING_PROPS[component.component as string];
    if (!prop) continue;
    const raw = (component as unknown as Record<string, unknown>)[prop];
    if (!isBinding(raw)) continue;
    const path = raw.path;
    if (!path || seenPaths.has(path)) continue;
    seenPaths.add(path);
    let key = inputKeyFromPath(path);
    // 路径末段撞名（`/a/x` 与 `/b/x`）时退回完整路径，保证字段可区分。
    if (seenKeys.has(key)) key = path;
    seenKeys.add(key);
    out.push({ path, key });
  }
  return out;
}

/** 绑定路径的末段作为回传字段名：`/target/labor` → `labor`。 */
export function inputKeyFromPath(path: string): string {
  const segments = parsePointer(path);
  return segments.length ? segments[segments.length - 1] : path;
}
