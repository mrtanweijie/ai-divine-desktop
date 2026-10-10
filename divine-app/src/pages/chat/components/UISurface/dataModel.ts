/**
 * 面板数据模型：RFC 6901 JSON Pointer 子集的取值 / 写值。
 *
 * 设计文档：`docs/design/028-a2ui-integration-20261009.md` §4.2 / §5.2。
 *
 * 只支持绑定形式 `{"path": "/a/b"}`（`catalog.py` 的 `BINDING_KEY`）。
 * 写值一律**不可变更新**（返回新对象），因为 `dataModel` 是
 * `UISurfaceBlock` 的 React state，原地改会让重渲染失效。
 */

import type { UIBindable, UIBinding } from "./types";

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
