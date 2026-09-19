import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import "./CollapsibleSection.less";

interface CollapsibleSectionProps {
  title: string;
  /** 收起时右侧的灰色说明，例如「未配置投递通道（任务仍会执行，只是不推送）」 */
  hint?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * 可折叠区块：点标题行展开/收起。
 *
 * 交互与样式对齐设置弹窗「模型配置 → 自定义设置」
 * （`components/SettingsModal/ModelSection.tsx`）：
 * - 用 `div + role="button"`，**不用原生 button**（项目约定，避免默认样式干扰）；
 * - ChevronDown 展开时旋转 180°；
 * - 收起时标题行高度与输入框对齐。
 */
export function CollapsibleSection({
  title,
  hint,
  defaultOpen = false,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  const toggle = () => setOpen((prev) => !prev);

  return (
    <div className={`collapsible-section${open ? " open" : ""}`}>
      <div
        className="collapsible-header"
        role="button"
        tabIndex={0}
        onClick={toggle}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            toggle();
          }
        }}
        aria-expanded={open}
      >
        <span className="collapsible-title">{title}</span>
        {!open && hint && <span className="collapsible-hint">{hint}</span>}
        <ChevronDown size={14} className="collapsible-chevron" />
      </div>
      {open && <div className="collapsible-body">{children}</div>}
    </div>
  );
}
