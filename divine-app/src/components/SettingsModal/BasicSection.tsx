import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, Keyboard } from "lucide-react";
import type { AppLocale } from "@/i18n";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import {
  DEFAULT_KEYMAP,
  formatShortcut,
  isMacPlatform,
} from "@/config/keymap";
import type { ThemePreference } from "@/services/theme";
import { UpdaterSection } from "./UpdaterSection";

interface SettingsBasicSectionProps {
  themePreference: ThemePreference;
  onThemeChange: (value: ThemePreference) => void;
  locale: AppLocale;
  onLocaleChange: (value: AppLocale) => void;
  username: string;
  onUsernameChange: (value: string) => void;
  contextLimit: number;
  onContextLimitChange: (value: number) => void;
  effort: string;
  onEffortChange: (value: string) => void;
  globalShortcutEnabled: boolean;
  onGlobalShortcutChange: (value: boolean) => void;
}

export function BasicSection({
  themePreference,
  onThemeChange,
  locale,
  onLocaleChange,
  username,
  onUsernameChange,
  contextLimit,
  onContextLimitChange,
  effort,
  onEffortChange,
  globalShortcutEnabled,
  onGlobalShortcutChange,
}: SettingsBasicSectionProps) {
  const { t } = useTranslation();
  const isMac = isMacPlatform();
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const appShortcuts = DEFAULT_KEYMAP.filter((def) => def.layer === "app");
  const globalShortcuts = DEFAULT_KEYMAP.filter(
    (def) => def.layer === "global"
  );

  return (
    <div className="settings-form">
      <Select
        label={t("settings.theme", "主题")}
        value={themePreference}
        onChange={(value) => onThemeChange(value as ThemePreference)}
        options={[
          { value: "dark", label: t("settings.themeDark", "深色") },
          { value: "light", label: t("settings.themeLight", "浅色") },
          { value: "system", label: t("settings.themeSystem", "跟随系统") },
        ]}
      />
      <Select
        label={t("settings.language", "语言")}
        value={locale}
        onChange={(value) => onLocaleChange(value as AppLocale)}
        options={[
          { value: "zh-CN", label: "简体中文" },
          { value: "zh-TW", label: "繁體中文" },
          { value: "en", label: "English" },
        ]}
      />
      <Input
        label={t("settings.username", "用户名")}
        value={username}
        onChange={(event) => onUsernameChange(event.target.value)}
        placeholder={t("settings.usernamePlaceholder", "用户")}
      />
      <Input
        label={t("settings.contextLimit", "上下文保留条数")}
        type="text"
        inputMode="numeric"
        value={contextLimit}
        onChange={(event) => {
          const digits = event.target.value.replace(/\D/g, "");
          onContextLimitChange(
            digits === "" ? 1 : Math.min(200, Number(digits))
          );
        }}
      />
      <Select
        label={
          <span className="settings-field-label-row">
            <span>{t("settings.thinkEffort", "深度思考")}</span>
            <span className="settings-field-hint-inline">
              {t(
                "settings.thinkEffortHint",
                "选择关闭则不进行深度思考；档位越高，思考越深入、响应越慢、消耗越多。"
              )}
            </span>
          </span>
        }
        value={effort}
        onChange={onEffortChange}
        options={[
          { value: "off", label: t("settings.effortOff", "关闭") },
          { value: "low", label: t("settings.effortLow", "低") },
          { value: "high", label: t("settings.effortHigh", "高") },
          { value: "max", label: t("settings.effortMax", "最高") },
        ]}
      />
      <div
        className={`settings-shortcut-card${
          shortcutsOpen ? " settings-shortcut-card--open" : ""
        }`}
      >
        <div
          className="settings-shortcut-summary"
          role="button"
          tabIndex={0}
          aria-expanded={shortcutsOpen}
          onClick={() => setShortcutsOpen((value) => !value)}
          onKeyDown={(event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            setShortcutsOpen((value) => !value);
          }}
          title={
            shortcutsOpen
              ? t("shortcuts.collapse", "收起")
              : t("shortcuts.expand", "展开")
          }
        >
          <Keyboard size={14} className="settings-shortcut-icon" />
          <span className="settings-shortcut-title">
            {t("shortcuts.title", "快捷键")}
          </span>
          <span className="settings-shortcut-count">
            {t("shortcuts.count", "{{total}} 项", {
              total: DEFAULT_KEYMAP.length,
            })}
          </span>
          <ChevronDown
            size={14}
            className={`settings-shortcut-chevron${
              shortcutsOpen ? " open" : ""
            }`}
          />
        </div>
        {shortcutsOpen && (
          <div className="settings-shortcut-list">
            {appShortcuts.map((def) => (
              <div key={def.id} className="settings-shortcut-row">
                <span className="settings-shortcut-label">
                  {t(def.labelKey, "")}
                </span>
                <kbd className="settings-shortcut-keys">
                  {formatShortcut(def, isMac)}
                </kbd>
              </div>
            ))}
            <div className="settings-shortcut-divider" />
            {globalShortcuts.map((def) => (
              <div key={def.id} className="settings-shortcut-row">
                <span className="settings-shortcut-label">
                  {t(def.labelKey, "")}
                </span>
                <span className="settings-shortcut-actions">
                  <Switch
                    checked={globalShortcutEnabled}
                    onChange={onGlobalShortcutChange}
                  />
                  <kbd className="settings-shortcut-keys">
                    {formatShortcut(def, isMac)}
                  </kbd>
                </span>
              </div>
            ))}
            <p className="settings-shortcut-hint">
              {t(
                "shortcuts.globalHint",
                "全局快捷键在任意应用中唤起或隐藏 Divine 主窗口。"
              )}
            </p>
          </div>
        )}
      </div>
      <UpdaterSection />
    </div>
  );
}
