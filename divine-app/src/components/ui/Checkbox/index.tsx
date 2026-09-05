import { Check } from "lucide-react";
import type { CSSProperties } from "react";
import "./index.less";

export interface CheckboxProps {
  checked: boolean;
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  /** 边长（px），默认 16 */
  size?: number;
  className?: string;
  ariaLabel?: string;
}

/** 通用复选框：勾选使用 Check 图标（lucide），颜色跟随主题 accent。
 * 用 span + role="checkbox" 实现（非 button），可安全嵌入按钮/卡片等容器；
 * 勾选视觉用内联样式控制（不依赖外部 CSS 加载），保证各环境稳定显示。 */
export function Checkbox({
  checked,
  onChange,
  disabled,
  size = 16,
  className,
  ariaLabel,
}: CheckboxProps) {
  const style = {
    width: size,
    height: size,
    ...(checked
      ? {
          background: "var(--color-accent)",
          borderColor: "var(--color-accent)",
          // accent 上的对比色：深色主题 accent=白 → 深图标；浅色主题 accent=深 → 白图标
          color: "var(--color-on-accent)",
        }
      : {}),
  } as CSSProperties;
  const handleToggle = () => {
    if (!disabled) onChange?.(!checked);
  };
  return (
    <span
      role="checkbox"
      aria-checked={checked}
      aria-label={ariaLabel}
      aria-disabled={disabled}
      tabIndex={disabled ? -1 : 0}
      className={`ui-checkbox${checked ? " checked" : ""}${
        disabled ? " disabled" : ""
      }${className ? ` ${className}` : ""}`}
      style={style}
      onClick={(event) => {
        // 阻止冒泡：勾选框被嵌在按钮/卡片内时，避免触发外层点击
        event.stopPropagation();
        handleToggle();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          event.stopPropagation();
          handleToggle();
        }
      }}
    >
      <Check size={size * 0.72} strokeWidth={3} style={{ opacity: checked ? 1 : 0 }} />
    </span>
  );
}
