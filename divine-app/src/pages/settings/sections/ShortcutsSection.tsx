import { ChevronDown, Keyboard } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Switch } from "@/components/ui/Switch";
import { DEFAULT_KEYMAP, formatShortcut, isMacPlatform } from "@/config/keymap";
import "./BasicSection.less";

interface ShortcutsSectionProps {
  globalShortcutEnabled: boolean;
  onGlobalShortcutChange: (value: boolean) => void;
}

/** 键盘快捷键（037）：应用内 + 全局快捷键列表；全局开关即时保存（父层处理）。 */
export function ShortcutsSection({
  globalShortcutEnabled,
  onGlobalShortcutChange,
}: ShortcutsSectionProps) {
  const { t } = useTranslation();
  const isMac = isMacPlatform();
  const appShortcuts = DEFAULT_KEYMAP.filter((def) => def.layer === "app");
  const globalShortcuts = DEFAULT_KEYMAP.filter((def) => def.layer === "global");

  return (
    <div className="settings-form">
      <div className="settings-shortcut-card settings-shortcut-card--open">
        <div
          className="settings-shortcut-summary"
          role="button"
          tabIndex={0}
          aria-expanded
          title={t("shortcuts.collapse", "收起")}
        >
          <Keyboard size={14} className="settings-shortcut-icon" />
          <span className="settings-shortcut-title">{t("shortcuts.title", "快捷键")}</span>
          <span className="settings-shortcut-count">
            {t("shortcuts.count", "{{total}} 项", { total: DEFAULT_KEYMAP.length })}
          </span>
          <ChevronDown size={14} className="settings-shortcut-chevron open" />
        </div>
        <div className="settings-shortcut-list">
          {appShortcuts.map((def) => (
            <div key={def.id} className="settings-shortcut-row">
              <span className="settings-shortcut-label">{t(def.labelKey, "")}</span>
              <kbd className="settings-shortcut-keys">{formatShortcut(def, isMac)}</kbd>
            </div>
          ))}
          <div className="settings-shortcut-divider" />
          {globalShortcuts.map((def) => (
            <div key={def.id} className="settings-shortcut-row">
              <span className="settings-shortcut-label">{t(def.labelKey, "")}</span>
              <span className="settings-shortcut-actions">
                <Switch checked={globalShortcutEnabled} onChange={onGlobalShortcutChange} />
                <kbd className="settings-shortcut-keys">{formatShortcut(def, isMac)}</kbd>
              </span>
            </div>
          ))}
          <p className="settings-shortcut-hint">
            {t("shortcuts.globalHint", "全局快捷键在任意应用中唤起或隐藏 Divine 主窗口。")}
          </p>
        </div>
      </div>
    </div>
  );
}
