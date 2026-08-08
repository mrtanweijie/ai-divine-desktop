import type { CSSProperties, HTMLAttributes, ReactNode } from "react";
import "./index.less";

const justifyMap: Record<string, CSSProperties["justifyContent"]> = {
  start: "flex-start",
  end: "flex-end",
  center: "center",
  "space-between": "space-between",
  "space-around": "space-around",
  "space-evenly": "space-evenly",
};

const alignMap: Record<string, CSSProperties["alignItems"]> = {
  start: "flex-start",
  end: "flex-end",
  center: "center",
  baseline: "baseline",
  stretch: "stretch",
};

export interface FlexProps extends HTMLAttributes<HTMLDivElement> {
  direction?: "row" | "column" | "row-reverse" | "column-reverse";
  justify?: keyof typeof justifyMap;
  align?: keyof typeof alignMap;
  wrap?: boolean;
  gap?: number | string;
  inline?: boolean;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}

export function Flex({
  direction = "row",
  justify = "start",
  align = "stretch",
  wrap = false,
  gap,
  inline = false,
  className,
  style,
  children,
  ...rest
}: FlexProps) {
  const flexStyle: CSSProperties = {
    display: inline ? "inline-flex" : "flex",
    flexDirection: direction,
    justifyContent: justifyMap[justify],
    alignItems: alignMap[align],
    flexWrap: wrap ? "wrap" : undefined,
    gap,
    ...style,
  };

  return (
    <div
      {...rest}
      className={`ui-flex${className ? ` ${className}` : ""}`}
      style={flexStyle}
    >
      {children}
    </div>
  );
}
