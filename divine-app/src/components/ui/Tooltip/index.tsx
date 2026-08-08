import type { ReactNode } from "react";
import "./index.less";

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
}

export function Tooltip({ content, children }: TooltipProps) {
  return (
    <span className="ui-tooltip-wrap">
      {children}
      <span className="ui-tooltip" role="tooltip">
        {content}
      </span>
    </span>
  );
}
