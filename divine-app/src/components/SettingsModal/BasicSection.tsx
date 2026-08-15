import { useTranslation } from "react-i18next";
import type { AppLocale } from "@/i18n";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
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
  thinkDefault: boolean;
  onThinkDefaultChange: (value: boolean) => void;
  reasoningEffort: string;
  onReasoningEffortChange: (value: string) => void;
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
  thinkDefault,
  onThinkDefaultChange,
  reasoningEffort,
  onReasoningEffortChange,
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
      <div className="ui-field">
        <span className="ui-field-label">
          {t("settings.thinkDefault", "默认深度思考")}
        </span>
        <Switch checked={thinkDefault} onChange={onThinkDefaultChange} />
      </div>
      <Select
        label={t("settings.reasoningEffort", "思考强度")}
        value={reasoningEffort}
        onChange={onReasoningEffortChange}
        options={[
          { value: "low", label: t("settings.effortLow", "低") },
          { value: "high", label: t("settings.effortHigh", "高") },
          { value: "max", label: t("settings.effortMax", "最高") },
        ]}
      />
      <p className="settings-field-hint">
        {t(
          "settings.reasoningEffortHint",
          "思考强度仅在开启深度思考时生效；档位越高，思考越深入、响应越慢、消耗越多。"
        )}
      </p>
      <UpdaterSection />
    </div>
  );
}
