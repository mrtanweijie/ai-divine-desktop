import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

const MODEL_OPTIONS = [
  { value: "deepseek-v4-flash", label: "deepseek-v4-flash" },
  { value: "deepseek-v4-pro", label: "deepseek-v4-pro" },
];

interface SettingsModelSectionProps {
  provider: string;
  onProviderChange: (value: string) => void;
  model: string;
  onModelChange: (value: string) => void;
  baseUrl: string;
  onBaseUrlChange: (value: string) => void;
  apiKey: string;
  onApiKeyChange: (value: string) => void;
  showKey: boolean;
  onToggleShowKey: () => void;
  glmApiKey: string;
  onGlmApiKeyChange: (value: string) => void;
  showGlmKey: boolean;
  onToggleShowGlmKey: () => void;
  hasApiKey: boolean;
  hasGlmKey: boolean;
}

export function ModelSection({
  provider,
  onProviderChange,
  model,
  onModelChange,
  baseUrl,
  onBaseUrlChange,
  apiKey,
  onApiKeyChange,
  showKey,
  onToggleShowKey,
  glmApiKey,
  onGlmApiKeyChange,
  showGlmKey,
  onToggleShowGlmKey,
  hasApiKey,
  hasGlmKey,
}: SettingsModelSectionProps) {
  const { t } = useTranslation();

  return (
    <div className="settings-form">
      <Select
        label="Provider"
        value={provider}
        onChange={onProviderChange}
        options={[
          { value: "auto", label: t("settings.providerAuto", "自动（有 Key 用 DeepSeek）") },
          { value: "langchain", label: t("settings.providerLangchain", "DeepSeek（ChatDeepSeek）") },
          { value: "mock", label: t("settings.providerMock", "本地演示") },
        ]}
      />
      <Select
        label={t("settings.model", "模型")}
        value={model}
        onChange={onModelChange}
        editable
        options={MODEL_OPTIONS}
        placeholder="deepseek-v4-flash"
      />
      <Input
        label="Base URL"
        value={baseUrl}
        onChange={(event) => onBaseUrlChange(event.target.value)}
        placeholder="https://api.deepseek.com"
      />
      <Input
        label={t("settings.apiKeyLabel", "API Key{{saved}}", {
          saved: hasApiKey ? t("settings.saved", "（已保存）") : "",
        })}
        type={showKey ? "text" : "password"}
        value={apiKey}
        onChange={(event) => onApiKeyChange(event.target.value)}
        placeholder="sk-..."
        autoComplete="off"
        action={
          <Button
            variant="icon"
            size="small"
            onClick={onToggleShowKey}
            aria-label={
              showKey
                ? t("settings.hideApiKey", "隐藏 API Key")
                : t("settings.showApiKey", "显示 API Key")
            }
          >
            {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
          </Button>
        }
      />
      <Input
        label={t("settings.glmApiKeyLabel", "GLM API Key（识图能力支持）{{saved}}", {
          saved: hasGlmKey ? t("settings.saved", "（已保存）") : "",
        })}
        type={showGlmKey ? "text" : "password"}
        value={glmApiKey}
        onChange={(event) => onGlmApiKeyChange(event.target.value)}
        placeholder="glm key..."
        autoComplete="off"
        action={
          <Button
            variant="icon"
            size="small"
            onClick={onToggleShowGlmKey}
            aria-label={
              showGlmKey
                ? t("settings.hideGlmApiKey", "隐藏 GLM API Key")
                : t("settings.showGlmApiKey", "显示 GLM API Key")
            }
          >
            {showGlmKey ? <EyeOff size={14} /> : <Eye size={14} />}
          </Button>
        }
      />
    </div>
  );
}
