import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import "./index.less";

export interface IconButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: ReactNode;
  /** 图标默认大小 13 */
  iconSize?: number;
  title?: string;
}

export function IconButton({
  icon,
  title,
  className,
  children,
  ...rest
}: IconButtonProps) {
  return (
    <Button
      variant="icon"
      className={`icon-button${className ? ` ${className}` : ""}`}
      title={title}
      aria-label={title}
      {...rest}
    >
      {icon}
    </Button>
  );
}
