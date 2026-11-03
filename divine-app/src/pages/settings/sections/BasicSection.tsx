import { useTranslation } from "react-i18next";
import type { AppLocale } from "@/i18n";
import type { ThemePreference } from "@/services/theme";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import type { SettingsSaveBody } from "@/types";
import { UpdaterSection } from "./UpdaterSection";
import "./BasicSection.less";

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
  /** 实时保存（037）：文本失焦 / 选择变更即持久化，无保存按钮 */
  onCommit: (body: SettingsSaveBody) => void;
}

/** 常规：主题 / 语言 / 用户名 / 上下文 / 思考档位 + 更新器。
 * 快捷键拆到 ShortcutsSection（037）；主题即时生效（useThemePreference 持久化），不走保存。 */
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
  onCommit,
}: SettingsBasicSectionProps) {
  const { t } = useTranslation();

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
        onBlur={() => onCommit({ username })}
        placeholder={t("settings.usernamePlaceholder", "用户")}
      />
      <Input
        label={t("settings.contextLimit", "上下文保留条数")}
        type="text"
        inputMode="numeric"
        value={contextLimit}
        onChange={(event) => {
          const digits = event.target.value.replace(/\D/g, "");
          onContextLimitChange(digits === "" ? 1 : Math.min(200, Number(digits)));
        }}
        onBlur={() => onCommit({ context_limit: contextLimit })}
      />
      <Select
        label={
          <span className="settings-field-label-row">
            <span>{t("settings.thinkEffort", "深度思考")}</span>
            <span className="settings-field-hint-inline">
              {t(
                "settings.thinkEffortHint",
                "选择关闭则不进行深度思考；档位越高，思考越深入、响应越慢、消耗越多。",
              )}
            </span>
          </span>
        }
        value={effort}
        onChange={(value) => {
          onEffortChange(value);
          onCommit({
            think_default: value !== "off",
            reasoning_effort: value === "off" ? "high" : value,
          });
        }}
        options={[
          { value: "off", label: t("settings.effortOff", "关闭") },
          { value: "low", label: t("settings.effortLow", "低") },
          { value: "high", label: t("settings.effortHigh", "高") },
          { value: "max", label: t("settings.effortMax", "最高") },
        ]}
      />
      <UpdaterSection />
    </div>
  );
}
