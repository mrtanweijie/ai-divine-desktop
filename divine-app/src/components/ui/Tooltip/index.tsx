import type { ReactNode } from "react";
import "./index.less";

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  /** 显示在包裹元素的上方（默认）还是下方 */
  placement?: "top" | "bottom";
  /** 水平对齐：居中（默认）或右对齐（贴近窗口右缘时避免溢出） */
  align?: "center" | "right";
}

export function Tooltip({ content, children, placement = "top", align = "center" }: TooltipProps) {
  const className = [
    "ui-tooltip-wrap",
    placement === "bottom" ? "tooltip-bottom" : "",
    align === "right" ? "tooltip-right" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={className}>
      {children}
      <span className="ui-tooltip" role="tooltip">
        {content}
      </span>
    </span>
  );
}
