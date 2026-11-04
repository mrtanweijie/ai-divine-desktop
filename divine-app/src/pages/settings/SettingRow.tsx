// SettingRow（037 §4.1）：行式设置卡——左「标题+描述」、右控件。
// 参考用户提供的 ZCode 式截图（2026-11-04）：卡片圆角边框、控件区右对齐定宽。
import type { ReactNode } from "react";
import "./SettingRow.less";

interface SettingRowProps {
  title: string;
  description?: string;
  /** 控件区（Select/Input 等），建议窄控件（~180px）右对齐 */
  children: ReactNode;
  /** 控件区宽度（px），默认 190 */
  controlWidth?: number;
}

export function SettingRow({ title, description, children, controlWidth = 190 }: SettingRowProps) {
  return (
    <div className="setting-row">
      <div className="setting-row-text">
        <div className="setting-row-title">{title}</div>
        {description && <div className="setting-row-desc">{description}</div>}
      </div>
      <div className="setting-row-control" style={{ width: controlWidth }}>
        {children}
      </div>
    </div>
  );
}
