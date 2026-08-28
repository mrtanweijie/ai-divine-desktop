import type { CSSProperties, ReactNode } from "react";
import "./index.less";

export type TagTone = "default" | "accent" | "success" | "danger" | "warning";

export interface TagProps {
  children?: ReactNode;
  /** 前置图标，如 <Star size={10} fill="currentColor" /> */
  icon?: ReactNode;
  /** 预设配色 */
  tone?: TagTone;
  /** 覆盖文字/图标颜色 */
  color?: string;
  /** 覆盖背景色 */
  background?: string;
  className?: string;
  style?: CSSProperties;
}

export function Tag({
  children,
  icon,
  tone = "default",
  color,
  background,
  className,
  style,
}: TagProps) {
  return (
    <span
      className={`ui-tag ui-tag--${tone}${className ? ` ${className}` : ""}`}
      style={{
        ...(color ? { color } : undefined),
        ...(background ? { background } : undefined),
        ...style,
      }}
    >
      {icon != null && <span className="ui-tag-icon">{icon}</span>}
      {children}
    </span>
  );
}
