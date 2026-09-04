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
      // 固定 small：缺省 medium 会命中 .ui-button--icon.ui-button--medium 的
      // 30px 盒（特异性 0,3,0），压过 .icon-button 的 24px（0,2,0），导致
      // 与显式 size="small" 的 Button--icon 并排时大小不一
      size="small"
      className={`icon-button${className ? ` ${className}` : ""}`}
      title={title}
      aria-label={title}
      {...rest}
    >
      {icon}
    </Button>
  );
}
