/**
 * 面板组件注册表：**组件名 → React 组件**。
 *
 * 设计文档：`docs/design/028-a2ui-integration-20261009.md` §4.2 / §7。
 *
 * 两条硬规则：
 * 1. **复用优先**：能映射到 `components/ui/` 现有控件的绝不重写
 *    （输入与按钮全部复用，保证 40px 高、token 圆角、深浅色一致）。
 * 2. **不引入第二套视觉**：自绘件（Card / Table / Steps / …）一律走
 *    `uis-` 前缀 + 现有 CSS token，不写死色值（044 §9.4）。
 */

import {
  Fragment,
  useEffect,
  useId,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { Tag, type TagTone } from "@/components/ui/Tag";
import { TextArea } from "@/components/ui/TextArea";
import { ChartBlock } from "@/pages/chat/components/ChartBlock";
import { chartHeight } from "@/pages/chat/components/ChartBlock/chartOptions";
import { GraphBlock, CANVAS_MIN_HEIGHT } from "@/pages/chat/components/GraphBlock";
import { ToolFileRow } from "@/pages/chat/components/MessageItem/ToolFileList";
import { isBinding } from "./dataModel";
import type {
  CompProps,
  SurfaceContext,
  UIBindable,
  UIComponentName,
  UIGap,
  UIJustify,
  UITone,
} from "./types";

// ---------------------------------------------------------------------------
// 常量映射
// ---------------------------------------------------------------------------

/** gap 语义 → px（与项目 8px 网格一致）。 */
const GAP_PX: Record<UIGap, number> = { none: 0, sm: 8, md: 12, lg: 20 };

/** justify 语义 → Flex 支持的取值。 */
const JUSTIFY_MAP: Record<UIJustify, "start" | "center" | "end" | "space-between"> = {
  start: "start",
  center: "center",
  end: "end",
  between: "space-between",
};

/** tone 语义 → Tag 预设配色。 */
const TAG_TONE: Record<UITone, TagTone> = {
  default: "default",
  primary: "accent",
  success: "success",
  warning: "warning",
  danger: "danger",
};

// ---------------------------------------------------------------------------
// 绑定读写
// ---------------------------------------------------------------------------

/**
 * 可绑定值的读写：有 `{path}` 就走 dataModel（受控 + 回流），
 * 字面量则退回组件本地 state（不可回流，边缘情况）。
 */
function useBoundValue<T>(
  ctx: SurfaceContext,
  value: UIBindable<T> | undefined,
  fallback: T,
): [T, (next: T) => void] {
  const path = isBinding(value) ? value.path : null;
  const [local, setLocal] = useState<T>(fallback);
  const resolved = ctx.resolve(value);
  const current: T = path ? ((resolved === undefined ? fallback : resolved) as T) : local;
  const write = (next: T) => {
    if (path) ctx.setValue(path, next);
    else setLocal(next);
  };
  return [current, write];
}

/** 取绑定路径；非绑定返回 null（写回时用）。 */
function bindingPath(value: unknown): string | null {
  return isBinding(value) ? value.path : null;
}

function renderCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

// ---------------------------------------------------------------------------
// A 组 · 布局
// ---------------------------------------------------------------------------

function ColumnComp({ component, ctx }: CompProps<"Column">) {
  return (
    <Flex
      className="uis-column"
      direction="column"
      gap={GAP_PX[component.gap ?? "md"]}
      align={component.align ?? "stretch"}
      justify={JUSTIFY_MAP[component.justify ?? "start"]}
    >
      {component.children.map((id) => (
        <Fragment key={id}>{ctx.renderChild(id)}</Fragment>
      ))}
    </Flex>
  );
}

function RowComp({ component, ctx }: CompProps<"Row">) {
  return (
    <Flex
      className="uis-row"
      direction="row"
      gap={GAP_PX[component.gap ?? "sm"]}
      align={component.align ?? "center"}
      wrap={Boolean(component.wrap)}
    >
      {component.children.map((id) => (
        <Fragment key={id}>{ctx.renderChild(id)}</Fragment>
      ))}
    </Flex>
  );
}

function CardComp({ component, ctx }: CompProps<"Card">) {
  const title = ctx.resolve(component.title);
  return (
    <div className={`uis-card tone-${component.tone ?? "default"}`}>
      {title ? <div className="uis-card-title">{title}</div> : null}
      <div className="uis-card-body">{ctx.renderChild(component.child)}</div>
    </div>
  );
}

function DividerComp({ component }: CompProps<"Divider">) {
  return <div className={`uis-divider is-${component.orientation ?? "horizontal"}`} />;
}

// ---------------------------------------------------------------------------
// B 组 · 展示
// ---------------------------------------------------------------------------

function TextComp({ component, ctx }: CompProps<"Text">) {
  const text = ctx.resolve(component.text) ?? "";
  const variant = component.variant ?? "body";
  const tone = component.tone ?? "default";
  return <div className={`uis-text is-${variant} tone-${tone}`}>{text}</div>;
}

function BadgeComp({ component, ctx }: CompProps<"Badge">) {
  const text = ctx.resolve(component.text) ?? "";
  return (
    <Tag className="uis-badge" tone={TAG_TONE[component.tone ?? "default"]}>
      {text}
    </Tag>
  );
}

function ImageComp({ component, ctx }: CompProps<"Image">) {
  const caption = ctx.resolve(component.caption);
  // 必填以预留高度（044 §16.4）；缺失时兜底 16/9，宁可比例不准也不让列表抖动。
  const ratio =
    typeof component.aspectRatio === "number" && component.aspectRatio > 0
      ? component.aspectRatio
      : 16 / 9;
  return (
    <figure className="uis-image">
      <div className="uis-image-box" style={{ aspectRatio: String(ratio) }}>
        <img src={component.url} alt={component.alt ?? ""} loading="lazy" decoding="async" />
      </div>
      {caption ? <figcaption className="uis-image-caption">{caption}</figcaption> : null}
    </figure>
  );
}

function TableComp({ component, ctx }: CompProps<"Table">) {
  const rows = ctx.resolve(component.rows) ?? [];
  const caption = ctx.resolve(component.caption);
  const columns = Array.isArray(component.columns) ? component.columns : [];
  return (
    <div className="uis-table-wrap">
      <div
        className="uis-table-scroll"
        style={component.maxHeight ? { maxHeight: component.maxHeight } : undefined}
      >
        <table className="uis-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  style={column.width ? { width: column.width } : undefined}
                >
                  {column.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((column) => (
                  <td key={column.key}>{renderCell(row?.[column.key])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {caption ? <div className="uis-table-caption">{caption}</div> : null}
    </div>
  );
}

function ProgressComp({ component, ctx }: CompProps<"Progress">) {
  const raw = Number(ctx.resolve(component.value) ?? 0);
  const value = Number.isFinite(raw) ? Math.max(0, Math.min(1, raw)) : 0;
  const label = ctx.resolve(component.label);
  return (
    <div className="uis-progress">
      <div className="uis-progress-head">
        <span className="uis-progress-label">{label ?? ""}</span>
        <span className="uis-progress-pct">{Math.round(value * 100)}%</span>
      </div>
      <div className="uis-progress-track">
        <div
          className={`uis-progress-bar tone-${component.tone ?? "default"}`}
          style={{ width: `${value * 100}%` }}
        />
      </div>
    </div>
  );
}

function StepsComp({ component, ctx }: CompProps<"Steps">) {
  const items = Array.isArray(component.items) ? component.items : [];
  const caption = ctx.resolve(component.caption);
  return (
    <div className="uis-steps">
      <ol className="uis-steps-list">
        {items.map((item, index) => (
          <li key={index} className={`uis-step is-${item.status}`}>
            <span className="uis-step-dot" aria-hidden="true" />
            <span className="uis-step-label">{item.label}</span>
          </li>
        ))}
      </ol>
      {caption ? <div className="uis-steps-caption">{caption}</div> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// C 组 · 输入
// ---------------------------------------------------------------------------

function TextFieldComp({ component, ctx }: CompProps<"TextField">) {
  const id = useId();
  const [value, setValue] = useBoundValue(ctx, component.value, "");
  return (
    <Input
      id={id}
      label={component.label}
      value={value}
      placeholder={component.placeholder}
      required={component.required}
      disabled={ctx.status !== "live"}
      onChange={(event) => setValue(event.target.value)}
    />
  );
}

function TextAreaComp({ component, ctx }: CompProps<"TextArea">) {
  const id = useId();
  const [value, setValue] = useBoundValue(ctx, component.value, "");
  return (
    <TextArea
      id={id}
      label={component.label}
      rows={component.rows ?? 4}
      value={value}
      disabled={ctx.status !== "live"}
      onChange={(event) => setValue(event.target.value)}
    />
  );
}

function NumberFieldComp({ component, ctx }: CompProps<"NumberField">) {
  const id = useId();
  const path = bindingPath(component.value);
  const resolved = ctx.resolve(component.value);
  const display = resolved === undefined || resolved === null ? "" : String(resolved);
  const disabled = ctx.status !== "live";
  const write = (text: string) => {
    if (!path) return;
    if (text === "") {
      ctx.setValue(path, "");
      return;
    }
    const parsed = Number(text);
    ctx.setValue(path, Number.isFinite(parsed) ? parsed : text);
  };
  return (
    <Input
      id={id}
      type="number"
      label={component.label}
      value={display}
      min={component.min}
      max={component.max}
      step={component.step}
      disabled={disabled}
      onChange={(event) => write(event.target.value)}
      action={component.unit ? <span className="uis-unit">{component.unit}</span> : undefined}
    />
  );
}

function SelectComp({ component, ctx }: CompProps<"Select">) {
  const path = bindingPath(component.value);
  const value = String(ctx.resolve(component.value) ?? "");
  const options = (Array.isArray(component.options) ? component.options : [])
    .filter((option) => option && typeof option.value === "string")
    .map((option) => ({ value: option.value, label: String(option.label ?? option.value) }));
  if (ctx.status !== "live") {
    // Select 无 disabled 语义：关闭态退化为只读文本，避免"能点但无效"。
    const current = options.find((option) => option.value === value);
    return (
      <div className="uis-readonly-field">
        <span className="ui-field-label">{component.label}</span>
        <span className="uis-readonly-value">{current?.label ?? value ?? "—"}</span>
      </div>
    );
  }
  return (
    <Select
      label={component.label}
      value={value}
      options={options}
      onChange={(next) => {
        if (path) ctx.setValue(path, next);
      }}
    />
  );
}

function ChoicePickerComp({ component, ctx }: CompProps<"ChoicePicker">) {
  const multiple = Boolean(component.multiple);
  const path = bindingPath(component.value);
  const raw = String(ctx.resolve(component.value) ?? "");
  const selected = multiple
    ? raw
        .split(/[,、]/)
        .map((item) => item.trim())
        .filter(Boolean)
    : raw
      ? [raw]
      : [];
  const options = (Array.isArray(component.options) ? component.options : []).filter(
    (option) => option && typeof option.value === "string",
  );
  const disabled = ctx.status !== "live";

  const toggle = (optionValue: string) => {
    if (disabled || !path) return;
    if (!multiple) {
      ctx.setValue(path, optionValue);
      return;
    }
    const next = selected.includes(optionValue)
      ? selected.filter((item) => item !== optionValue)
      : [...selected, optionValue];
    ctx.setValue(path, next.join(","));
  };

  return (
    <div className="uis-choice" role={multiple ? "group" : "radiogroup"}>
      {options.map((option) => {
        const active = selected.includes(option.value);
        return (
          <div
            key={option.value}
            role={multiple ? "checkbox" : "radio"}
            aria-checked={active}
            aria-disabled={disabled}
            tabIndex={disabled ? -1 : 0}
            className={`uis-choice-item${active ? " is-active" : ""}${
              disabled ? " is-disabled" : ""
            }`}
            onClick={() => toggle(option.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                toggle(option.value);
              }
            }}
          >
            <span className="uis-choice-label">{option.label}</span>
            {option.desc ? <span className="uis-choice-desc">{option.desc}</span> : null}
          </div>
        );
      })}
    </div>
  );
}

function CheckboxComp({ component, ctx }: CompProps<"Checkbox">) {
  const path = bindingPath(component.checked);
  const checked = Boolean(ctx.resolve(component.checked));
  return (
    <div className="uis-check-row">
      <Checkbox
        checked={checked}
        disabled={ctx.status !== "live"}
        ariaLabel={component.label}
        onChange={(next) => {
          if (path) ctx.setValue(path, next);
        }}
      />
      <span className="uis-check-label">{component.label}</span>
    </div>
  );
}

function SwitchComp({ component, ctx }: CompProps<"Switch">) {
  const path = bindingPath(component.checked);
  const checked = Boolean(ctx.resolve(component.checked));
  return (
    <Switch
      checked={checked}
      label={component.label}
      disabled={ctx.status !== "live"}
      onChange={(next) => {
        if (path) ctx.setValue(path, next);
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// D 组 · 动作
// ---------------------------------------------------------------------------

function ButtonComp({ component, ctx }: CompProps<"Button">) {
  const text = ctx.resolve(component.text) ?? "";
  // pendingActionId 语义：**正在提交的组件 id**（乐观态，见 UISurfaceBlock）。
  const pending = ctx.pendingActionId === component.id;
  const disabled = Boolean(component.disabled) || ctx.status !== "live";
  const variant =
    component.variant === "ghost" ? "ghost" : component.variant === "danger" ? "danger" : "primary";
  return (
    <Button
      variant={variant}
      className="uis-button"
      loading={pending}
      disabled={disabled || pending}
      onClick={() => ctx.submit(component.action, component.id, text)}
    >
      {text}
    </Button>
  );
}

// ---------------------------------------------------------------------------
// E 组 · 富媒体（S5）
//

/**
 * 重组件懒挂载：**未进视口只渲染等高空占位**（044 §16.2）。
 *
 * `MessageList` 的虚拟列表 `overscan: 12` 会把屏幕外十几项一起 mount，
 * 而 ChartBlock 的 effect 每次触发都是 `dispose` + `echarts.init` 重建、
 * GraphBlock 更重（X6 异步创建 + 布局 + measure）。没有这道闸门时，
 * 滚动路径上的离屏面板会一起初始化。
 *
 * `height` 必须与子组件挂载后的初始高度一致，否则等于把 §16.4 的
 * "面板挂载后高度再变 → 虚拟列表重测 → 滚动跳"重新引入一遍。
 */
function LazyMount({
  height,
  className,
  children,
}: {
  height: number;
  className?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // 无 IntersectionObserver（老内核）时初始即视为可见：宁可稍慢也要能看见。
  // 写成 useState 的初值而不是在 effect 里 setState —— 后者会触发一轮
  // 级联渲染（react-hooks/set-state-in-effect）。
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === "undefined");

  useEffect(() => {
    if (visible) return;
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      // 上下各预取 200px：滚动到跟前时已经开始初始化。
      { rootMargin: "200px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [visible]);

  return (
    <div ref={ref} className={className} style={visible ? undefined : { height }}>
      {visible ? children : null}
    </div>
  );
}

function ChartComp({ component, ctx }: CompProps<"Chart">) {
  const caption = ctx.resolve(component.caption);
  // 占位高度用 ChartBlock 的同一套算法（chartHeight），挂载前后完全等高。
  const height =
    typeof component.height === "number" && component.height > 0
      ? Math.max(component.height, 120)
      : chartHeight(component.option);
  return (
    <div className="uis-media">
      <LazyMount height={height} className="uis-media-slot">
        <ChartBlock option={component.option} workspacePath={ctx.workspacePath} />
      </LazyMount>
      {caption ? <div className="uis-media-caption">{caption}</div> : null}
    </div>
  );
}

function GraphComp({ component, ctx }: CompProps<"Graph">) {
  const caption = ctx.resolve(component.caption);
  // GraphBlock 自己也会先渲染一个 CANVAS_MIN_HEIGHT 占位再按 measure 调整，
  // 这里取两者较大值，保证懒挂载前后不会「先矮后高」。
  const reserved =
    typeof component.height === "number" && component.height > 0
      ? Math.max(component.height, CANVAS_MIN_HEIGHT)
      : CANVAS_MIN_HEIGHT;
  return (
    <div className="uis-media">
      <LazyMount height={reserved} className="uis-media-slot">
        {/* animate=false：面板是原子渲染的静态产物，不做入场动画（§5.1） */}
        <GraphBlock ir={component.ir} workspacePath={ctx.workspacePath} animate={false} />
      </LazyMount>
      {caption ? <div className="uis-media-caption">{caption}</div> : null}
    </div>
  );
}

function FileListComp({ component, ctx }: CompProps<"FileList">) {
  const caption = ctx.resolve(component.caption);
  const files = Array.isArray(component.files) ? component.files : [];
  return (
    <div className="uis-filelist">
      {/* 复用 ToolFileList 的行样式（044 §4.2：FileList 只做 props 转发） */}
      <div className="file-actions file-list">
        {files.map((file) => (
          <ToolFileRow key={file.path ?? file.name} file={file} workspacePath={ctx.workspacePath} />
        ))}
      </div>
      {caption ? <div className="uis-media-caption">{caption}</div> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 注册表
// ---------------------------------------------------------------------------

/** 组件名 → 渲染组件。**新增组件只改这里 + `types.ts` 的属性表**。 */
export const COMPONENT_REGISTRY: {
  [K in UIComponentName]: ComponentType<CompProps<K>>;
} = {
  Column: ColumnComp,
  Row: RowComp,
  Card: CardComp,
  Divider: DividerComp,
  Text: TextComp,
  Badge: BadgeComp,
  Image: ImageComp,
  Table: TableComp,
  Progress: ProgressComp,
  Steps: StepsComp,
  TextField: TextFieldComp,
  TextArea: TextAreaComp,
  NumberField: NumberFieldComp,
  Select: SelectComp,
  ChoicePicker: ChoicePickerComp,
  Checkbox: CheckboxComp,
  Switch: SwitchComp,
  Button: ButtonComp,
  Chart: ChartComp,
  Graph: GraphComp,
  FileList: FileListComp,
};

/** 按 id 渲染一个组件节点（供块内递归调用）。 */
export function renderComponentNode(
  name: UIComponentName,
  component: unknown,
  ctx: SurfaceContext,
): ReactNode {
  const Impl = COMPONENT_REGISTRY[name] as unknown as ComponentType<{
    component: unknown;
    ctx: SurfaceContext;
  }>;
  if (!Impl) return null;
  return <Impl component={component} ctx={ctx} />;
}
