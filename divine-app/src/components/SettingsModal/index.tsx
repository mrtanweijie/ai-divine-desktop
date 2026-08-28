import { useEffect, useState } from "react";
import { AudioWaveform, Cpu, Info, Save, Settings2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import tauriConfig from "../../../src-tauri/tauri.conf.json";
import type {
  ModelConfig,
  Settings,
  SettingsSaveBody,
} from "@/types";
import {
  readLocalePreference,
  setLocale,
  type AppLocale,
} from "@/i18n";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { getAppVersion } from "@/services/tauri";
import { setSettingsOpen } from "@/services/updater";
import {
  useThemePreference,
  type ThemePreference,
} from "@/services/theme";
import { AboutSection } from "./AboutSection";
import { BasicSection } from "./BasicSection";
import { ModelSection } from "./ModelSection";
import { LocalLLMSection } from "./LocalLLMSection";
import "./index.less";

/** Build a UI-ready model list from server settings, tolerating servers that
 * don't return `models` yet (single legacy entry derived from top-level). */
function modelsFromSettings(settings: Settings): ModelConfig[] {
  if (Array.isArray(settings.models) && settings.models.length > 0) {
    return settings.models.map((entry) => ({ ...entry }));
  }
  const legacyProvider =
    settings.provider === "auto" ||
    settings.provider === "langchain" ||
    settings.provider === "mock"
      ? settings.provider
      : "langchain";
  return [
    {
      id: "default",
      name: settings.model || "DeepSeek V4 Flash",
      provider: legacyProvider,
      model: settings.model || "deepseek-v4-flash",
      base_url: settings.base_url || "https://api.deepseek.com",
      has_api_key: settings.has_api_key,
      active: true,
    },
  ];
}

interface SettingsModalProps {
  settings: Settings;
  onClose: () => void;
  onSave: (body: SettingsSaveBody) => Promise<void> | void;
  /** 静默保存（不关闭弹窗） */
  onSilentSave?: (body: SettingsSaveBody) => Promise<void> | void;
  onConfirm?: (title: string, description: string, action: () => void) => void;
}

export function SettingsModal({
  settings,
  onClose,
  onSave,
  onSilentSave,
  onConfirm,
}: SettingsModalProps) {
  const { t } = useTranslation();
  const [locale, setLocaleState] = useState<AppLocale>(readLocalePreference);
  const [models, setModels] = useState<ModelConfig[]>(() =>
    modelsFromSettings(settings)
  );
  const [modelKeys, setModelKeys] = useState<Record<string, string>>({});
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [glmApiKey, setGlmApiKey] = useState("");
  const [username, setUsername] = useState(settings.username);
  const [effort, setEffort] = useState(
    settings.think_default ? settings.reasoning_effort ?? "high" : "off"
  );
  const [contextLimit, setContextLimit] = useState(settings.context_limit);
  const [showGlmKey, setShowGlmKey] = useState(false);
  const [version, setVersion] = useState(`v${tauriConfig.version}`);
  const [themePreference, setThemePreferenceState] = useThemePreference();
  const [section, setSection] = useState<"basic" | "model" | "local" | "about">("basic");
  const [localLLMEnabled, setLocalLLMEnabled] = useState(settings.local_llm_enabled ?? false);
  const [localLLMMode, setLocalLLMMode] = useState<"keyword" | "local" | "hybrid">(
    settings.local_llm_mode ?? "keyword"
  );

  useEffect(() => {
    setSettingsOpen(true);
    return () => setSettingsOpen(false);
  }, []);

  useEffect(() => {
    setModels(modelsFromSettings(settings));
    setModelKeys({});
    setShowKeys({});
    setUsername(settings.username);
    setEffort(
      settings.think_default ? settings.reasoning_effort ?? "high" : "off"
    );
    setContextLimit(settings.context_limit);
    setLocalLLMEnabled(settings.local_llm_enabled ?? false);
    setLocalLLMMode(settings.local_llm_mode ?? "keyword");
  }, [settings]);

  useEffect(() => {
    let active = true;
    void getAppVersion().then((value) => {
      if (active && value) setVersion(`v${value}`);
    });
    return () => {
      active = false;
    };
  }, []);

  // 每个 tab 只保存自己的字段：通用 tab 不触碰模型配置，
  // 模型 tab 的密钥仅在用户输入新值时提交，避免把已保存的 Key 覆盖为空。
  const saveCurrentSection = () => {
    if (section === "basic") {
      void onSave({
        username,
        think_default: effort !== "off",
        reasoning_effort: effort === "off" ? "high" : effort,
        context_limit: contextLimit,
      });
      return;
    }
    if (section === "model") {
      const body: SettingsSaveBody = {
        models: models.map((entry) => ({
          id: entry.id,
          name: entry.name,
          provider: entry.provider,
          model: entry.model,
          base_url: entry.base_url,
          active: entry.active,
          tool_mode: entry.tool_mode ?? "auto",
          custom_models: entry.custom_models ?? "",
          vendor: entry.vendor ?? "",
          // 空字符串 = 保持不变，服务端保留已保存的 Key
          api_key: modelKeys[entry.id] ?? "",
        })),
      };
      const trimmedGlmKey = glmApiKey.trim();
      if (trimmedGlmKey) body.glm_api_key = trimmedGlmKey;
      void onSave(body);
    }
    if (section === "local") {
      void onSave({
        local_llm_enabled: localLLMEnabled,
        local_llm_mode: localLLMMode,
      });
    }
  };

  // 设为默认后自动保存模型配置（不关闭弹窗）
  const handleAutoSaveModels = (newModels: ModelConfig[]) => {
    const body: SettingsSaveBody = {
      models: newModels.map((entry) => ({
        id: entry.id,
        name: entry.name,
        provider: entry.provider,
        model: entry.model,
        base_url: entry.base_url,
        active: entry.active,
        tool_mode: entry.tool_mode ?? "auto",
        custom_models: entry.custom_models ?? "",
        vendor: entry.vendor ?? "",
        api_key: modelKeys[entry.id] ?? "",
      })),
    };
    void (onSilentSave ?? onSave)(body);
  };

  return (
    <Modal
      open
      title={t("settings.title", "设置")}
      titleSuffix={version}
      onClose={onClose}
      width={800}
      headerAction={
        <Button
          variant="icon"
          onClick={onClose}
          aria-label={t("common.close", "关闭")}
          title={t("common.close", "关闭")}
        >
          <X size={16} />
        </Button>
      }
      footer={
        section !== "about" ? (
          <>
            <Button variant="secondary" onClick={onClose}>
              {t("common.cancel", "取消")}
            </Button>
            <Button variant="primary" onClick={saveCurrentSection}>
              <Save size={15} />
              {t("common.save", "保存")}
            </Button>
          </>
        ) : undefined
      }
    >
      <div className="settings-layout">
        <div className="settings-sidebar">
          <button
            type="button"
            className={`settings-nav-item${
              section === "basic" ? " active" : ""
            }`}
            onClick={() => setSection("basic")}
          >
            <Settings2 size={15} />
            <span>{t("settings.sectionGeneral", "通用")}</span>
          </button>
          <button
            type="button"
            className={`settings-nav-item${
              section === "model" ? " active" : ""
            }`}
            onClick={() => setSection("model")}
          >
            <Cpu size={15} />
            <span>{t("settings.sectionModel", "模型")}</span>
          </button>
          <button
            type="button"
            className={`settings-nav-item${
              section === "local" ? " active" : ""
            }`}
            onClick={() => setSection("local")}
          >
            <AudioWaveform size={15} />
            <span>{t("settings.sectionLocal", "意图")}</span>
          </button>
          <button
            type="button"
            className={`settings-nav-item${
              section === "about" ? " active" : ""
            }`}
            onClick={() => setSection("about")}
          >
            <Info size={15} />
            <span>{t("about.title", "关于")}</span>
          </button>
        </div>
        <div className="settings-main">
          {section === "basic" ? (
            <BasicSection
              themePreference={themePreference}
              onThemeChange={(value: ThemePreference) =>
                setThemePreferenceState(value)
              }
              locale={locale}
              onLocaleChange={(value) => {
                setLocaleState(value);
                setLocale(value);
              }}
              username={username}
              onUsernameChange={setUsername}
              contextLimit={contextLimit}
              onContextLimitChange={setContextLimit}
              effort={effort}
              onEffortChange={setEffort}
            />
          ) : section === "model" ? (
            <ModelSection
              models={models}
              onModelsChange={setModels}
              modelKeys={modelKeys}
              onModelKeyChange={(id, value) =>
                setModelKeys((prev) => ({ ...prev, [id]: value }))
              }
              showKeys={showKeys}
              onToggleShowKey={(id) =>
                setShowKeys((prev) => ({ ...prev, [id]: !prev[id] }))
              }
              glmApiKey={glmApiKey}
              onGlmApiKeyChange={setGlmApiKey}
              showGlmKey={showGlmKey}
              onToggleShowGlmKey={() => setShowGlmKey((value) => !value)}
              hasGlmKey={settings.has_glm_key}
              onConfirm={onConfirm}
              onAutoSave={handleAutoSaveModels}
            />
          ) : section === "local" ? (
            <LocalLLMSection
              localLLMEnabled={localLLMEnabled}
              localLLMMode={localLLMMode}
              onModeChange={setLocalLLMMode}
            />
          ) : (
            <AboutSection />
          )}
        </div>
      </div>
    </Modal>
  );
}
