import { useTranslation } from "react-i18next";
import type { AppLocale } from "@/i18n";
import type { ThemePreference } from "@/services/theme";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { SettingRow } from "../SettingRow";
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
      <SettingRow
        title={t("settings.theme", "主题")}
        description={t("settings.themeDesc", "切换应用的深色 / 浅色外观。")}
      >
        <Select
          value={themePreference}
          onChange={(value) => onThemeChange(value as ThemePreference)}
          options={[
            { value: "dark", label: t("settings.themeDark", "深色") },
            { value: "light", label: t("settings.themeLight", "浅色") },
            { value: "system", label: t("settings.themeSystem", "跟随系统") },
          ]}
        />
      </SettingRow>
      <SettingRow
        title={t("settings.language", "界面语言")}
        description={t("settings.languageDesc", "选择应用 UI 的显示语言。")}
      >
        <Select
          value={locale}
          onChange={(value) => onLocaleChange(value as AppLocale)}
          options={[
            { value: "zh-CN", label: "简体中文" },
            { value: "zh-TW", label: "繁體中文" },
            { value: "en", label: "English" },
          ]}
        />
      </SettingRow>
      <SettingRow
        title={t("settings.username", "用户名")}
        description={t("settings.usernameDesc", "AI 在对话中如何称呼你。")}
      >
        <Input
          value={username}
          onChange={(event) => onUsernameChange(event.target.value)}
          onBlur={() => onCommit({ username })}
          placeholder={t("settings.usernamePlaceholder", "用户")}
        />
      </SettingRow>
      <SettingRow
        title={t("settings.contextLimit", "上下文保留条数")}
        description={t("settings.contextLimitDesc", "对话中保留的历史消息条数，越大越耗上下文。")}
      >
        <Input
          type="text"
          inputMode="numeric"
          value={contextLimit}
          onChange={(event) => {
            const digits = event.target.value.replace(/\D/g, "");
            onContextLimitChange(digits === "" ? 1 : Math.min(200, Number(digits)));
          }}
          onBlur={() => onCommit({ context_limit: contextLimit })}
        />
      </SettingRow>
      <SettingRow
        title={t("settings.thinkEffort", "深度思考")}
        description={t(
          "settings.thinkEffortHint",
          "选择关闭则不进行深度思考；档位越高，思考越深入、响应越慢、消耗越多。",
        )}
      >
        <Select
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
      </SettingRow>
      <UpdaterSection />
    </div>
  );
}
