import { useEffect, useState } from "react";
import { AudioWaveform, Blocks, Brain, Cpu, Info, Save, Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import tauriConfig from "../../../src-tauri/tauri.conf.json";
import type { ModelConfig, Settings, SettingsSaveBody } from "@/types";
import { readLocalePreference, setLocale, type AppLocale } from "@/i18n";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { getAppVersion, isTauri, setGlobalShortcutEnabled } from "@/services/tauri";
import { setSettingsOpen } from "@/services/updater";
import { useThemePreference, type ThemePreference } from "@/services/theme";
import { AboutSection } from "./AboutSection";
import { BasicSection } from "./BasicSection";
import { McpSection } from "./McpSection";
import { ModelSection } from "./ModelSection";
import { LocalLLMSection } from "./LocalLLMSection";
import { BrowserSection } from "./BrowserSection";
import { MemorySection } from "./MemorySection";
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
      model: settings.model || "deepseek-flash",
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
  /** 打开时定位到的 tab（默认"通用"） */
  initialSection?: "basic" | "model" | "mcp" | "local" | "memory" | "about";
}

export function SettingsModal({
  settings,
  onClose,
  onSave,
  onSilentSave,
  onConfirm,
  initialSection = "basic",
}: SettingsModalProps) {
  const { t } = useTranslation();
  const [locale, setLocaleState] = useState<AppLocale>(readLocalePreference);
  const [models, setModels] = useState<ModelConfig[]>(() => modelsFromSettings(settings));
  const [modelKeys, setModelKeys] = useState<Record<string, string>>({});
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [glmApiKey, setGlmApiKey] = useState("");
  const [username, setUsername] = useState(settings.username);
  const [effort, setEffort] = useState(
    settings.think_default ? (settings.reasoning_effort ?? "high") : "off",
  );
  const [contextLimit, setContextLimit] = useState(settings.context_limit);
  const [showGlmKey, setShowGlmKey] = useState(false);
  const [version, setVersion] = useState(`v${tauriConfig.version}`);
  const [themePreference, setThemePreferenceState] = useThemePreference();
  const [section, setSection] = useState<"basic" | "model" | "mcp" | "local" | "memory" | "about">(
    initialSection,
  );
  const [localLLMEnabled, setLocalLLMEnabled] = useState(settings.local_llm_enabled ?? false);
  const [localLLMMode, setLocalLLMMode] = useState<"keyword" | "local" | "hybrid">(
    settings.local_llm_mode ?? "keyword",
  );
  const [globalShortcutEnabled, setGlobalShortcutEnabledState] = useState(
    settings.global_shortcut_enabled !== false,
  );

  useEffect(() => {
    setSettingsOpen(true);
    return () => setSettingsOpen(false);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- settings 更新后镜像到本地表单态（多字段派生同步）
    setModels(modelsFromSettings(settings));
    setModelKeys({});
    setShowKeys({});
    setUsername(settings.username);
    setEffort(settings.think_default ? (settings.reasoning_effort ?? "high") : "off");
    setContextLimit(settings.context_limit);
    setLocalLLMEnabled(settings.local_llm_enabled ?? false);
    setLocalLLMMode(settings.local_llm_mode ?? "keyword");
    setGlobalShortcutEnabledState(settings.global_shortcut_enabled !== false);
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

  // 全局快捷键开关：立即持久化并即时注册/注销（不经过"保存"按钮）
  const handleGlobalShortcutChange = (value: boolean) => {
    setGlobalShortcutEnabledState(value);
    void (onSilentSave ?? onSave)({ global_shortcut_enabled: value });
    if (isTauri()) {
      void setGlobalShortcutEnabled(value).catch(() => {
        // 注册失败（如被其他应用占用）：回滚 UI，下次打开设置同步真实状态
        setGlobalShortcutEnabledState(!value);
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
      width={860}
      footer={
        // 意图 tab 的操作（模式切换/模型启停）即时生效，无需底部保存按钮
        section !== "about" && section !== "local" && section !== "mcp" && section !== "memory" ? (
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
          <div
            role="tab"
            aria-selected={section === "basic"}
            tabIndex={0}
            className={`settings-nav-item${section === "basic" ? " active" : ""}`}
            onClick={() => setSection("basic")}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setSection("basic");
              }
            }}
          >
            <Settings2 size={15} />
            <span>{t("settings.sectionGeneral", "通用")}</span>
          </div>
          <div
            role="tab"
            aria-selected={section === "model"}
            tabIndex={0}
            className={`settings-nav-item${section === "model" ? " active" : ""}`}
            onClick={() => setSection("model")}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setSection("model");
              }
            }}
          >
            <Cpu size={15} />
            <span>{t("settings.sectionModel", "模型")}</span>
          </div>
          <div
            role="tab"
            aria-selected={section === "mcp"}
            tabIndex={0}
            className={`settings-nav-item${section === "mcp" ? " active" : ""}`}
            onClick={() => setSection("mcp")}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setSection("mcp");
              }
            }}
          >
            <Blocks size={15} />
            <span>{t("settings.sectionMcp", "MCP")}</span>
          </div>
          <div
            role="tab"
            aria-selected={section === "local"}
            tabIndex={0}
            className={`settings-nav-item${section === "local" ? " active" : ""}`}
            onClick={() => setSection("local")}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setSection("local");
              }
            }}
          >
            <AudioWaveform size={15} />
            <span>{t("settings.sectionLocal", "意图")}</span>
          </div>
          <div
            role="tab"
            aria-selected={section === "memory"}
            tabIndex={0}
            className={`settings-nav-item${section === "memory" ? " active" : ""}`}
            onClick={() => setSection("memory")}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setSection("memory");
              }
            }}
          >
            <Brain size={15} />
            <span>{t("settings.sectionMemory", "记忆")}</span>
          </div>
          <div
            role="tab"
            aria-selected={section === "about"}
            tabIndex={0}
            className={`settings-nav-item${section === "about" ? " active" : ""}`}
            onClick={() => setSection("about")}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setSection("about");
              }
            }}
          >
            <Info size={15} />
            <span>{t("about.title", "关于")}</span>
          </div>
        </div>
        <div className="settings-main">
          {section === "basic" ? (
            <>
              <BasicSection
                themePreference={themePreference}
                onThemeChange={(value: ThemePreference) => setThemePreferenceState(value)}
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
                globalShortcutEnabled={globalShortcutEnabled}
                onGlobalShortcutChange={handleGlobalShortcutChange}
              />
              <BrowserSection />
            </>
          ) : section === "model" ? (
            <ModelSection
              models={models}
              onModelsChange={setModels}
              modelKeys={modelKeys}
              onModelKeyChange={(id, value) => setModelKeys((prev) => ({ ...prev, [id]: value }))}
              showKeys={showKeys}
              onToggleShowKey={(id) => setShowKeys((prev) => ({ ...prev, [id]: !prev[id] }))}
              glmApiKey={glmApiKey}
              onGlmApiKeyChange={setGlmApiKey}
              showGlmKey={showGlmKey}
              onToggleShowGlmKey={() => setShowGlmKey((value) => !value)}
              hasGlmKey={settings.has_glm_key}
              onConfirm={onConfirm}
              onAutoSave={handleAutoSaveModels}
            />
          ) : section === "mcp" ? (
            <McpSection
              initialServers={settings.mcp_servers}
              onSave={onSave}
              onSilentSave={onSilentSave}
              onConfirm={onConfirm}
            />
          ) : section === "local" ? (
            <LocalLLMSection
              localLLMEnabled={localLLMEnabled}
              localLLMMode={localLLMMode}
              onModeChange={setLocalLLMMode}
            />
          ) : section === "memory" ? (
            <MemorySection onConfirm={onConfirm} />
          ) : (
            <AboutSection />
          )}
        </div>
      </div>
    </Modal>
  );
}
