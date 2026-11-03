// 设置面板（037）：整页视图（view=settings），替代原 SettingsModal 弹窗。
// 8 个 section 组件原样复用（./sections/），basic 拆出 外观 / 键盘快捷键 两个薄页。
// 保存模型 P1 维持分区「保存」按钮；section 深链走 ?view=settings&section=x。
import { useEffect, useState } from "react";
import {
  AudioWaveform,
  Blocks,
  Brain,
  ChevronLeft,
  Cpu,
  Film,
  Globe,
  Info,
  Keyboard,
  Save,
  Settings2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import tauriConfig from "../../../src-tauri/tauri.conf.json";
import type { ModelConfig, Settings, SettingsSaveBody } from "@/types";
import {
  MediaSection,
  toMediaDraft,
  toMediaPayload,
  type MediaModelDraft,
} from "./sections/MediaSection";
import { readLocalePreference, setLocale, type AppLocale } from "@/i18n";
import { Button } from "@/components/ui/Button";
import { getAppVersion, isTauri, setGlobalShortcutEnabled } from "@/services/tauri";
import { useThemePreference, type ThemePreference } from "@/services/theme";
import { AboutSection } from "./sections/AboutSection";
import { BasicSection } from "./sections/BasicSection";
import { McpSection } from "./sections/McpSection";
import { ModelSection } from "./sections/ModelSection";
import { LocalLLMSection } from "./sections/LocalLLMSection";
import { BrowserSection } from "./sections/BrowserSection";
import { MemorySection } from "./sections/MemorySection";
import { ShortcutsSection } from "./sections/ShortcutsSection";
import "./sections/shared.less";
import "./index.less";

export type SettingsSection =
  "basic" | "shortcuts" | "model" | "media" | "mcp" | "local" | "memory" | "browser" | "about";

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

interface SettingsPageProps {
  settings: Settings;
  section: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
  onBack: () => void;
  onSave: (body: SettingsSaveBody) => Promise<void> | void;
  /** 静默保存（不离开页面） */
  onSilentSave?: (body: SettingsSaveBody) => Promise<void> | void;
  onConfirm?: (title: string, description: string, action: () => void) => void;
}

export function SettingsPage({
  settings,
  section,
  onSectionChange,
  onBack,
  onSave,
  onSilentSave,
  onConfirm,
}: SettingsPageProps) {
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
  const [mediaModels, setMediaModels] = useState<MediaModelDraft[]>(() =>
    (settings.media_models ?? []).map(toMediaDraft),
  );
  const [localLLMEnabled, setLocalLLMEnabled] = useState(settings.local_llm_enabled ?? false);
  const [localLLMMode, setLocalLLMMode] = useState<"keyword" | "local" | "hybrid">(
    settings.local_llm_mode ?? "keyword",
  );
  const [globalShortcutEnabled, setGlobalShortcutEnabledState] = useState(
    settings.global_shortcut_enabled !== false,
  );

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
    setMediaModels((settings.media_models ?? []).map(toMediaDraft));
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

  // 整页拖拽：wry 要求 target 精确命中带属性元素，主要布局容器都要挂
  const dragRegionProps = isTauri() ? { "data-tauri-drag-region": true } : {};

  // ESC 返回工作区（原 modal 的 ESC 关闭语义平移）
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onBack();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onBack]);

  // 每个 tab 只保存自己的字段：通用 tab 不触碰模型配置，
  // 模型 tab 的密钥仅在用户输入新值时提交，避免把已保存的 Key 覆盖为空。
  const saveCurrentSection = () => {
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
    if (section === "media") {
      // 生成模型（036/035）：与模型页同语义——空 key 保留已存值
      void onSave({ media_models: toMediaPayload(mediaModels) });
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

  // 设为默认后自动保存模型配置（不离开页面）
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

  const navGroups: Array<{
    label: string;
    items: Array<{ id: SettingsSection; icon: typeof Cpu; label: string }>;
  }> = [
    {
      label: t("settings.groupBasic", "基础设置"),
      items: [
        { id: "basic", icon: Settings2, label: t("settings.sectionGeneral", "常规") },
        { id: "shortcuts", icon: Keyboard, label: t("settings.sectionShortcuts", "键盘快捷键") },
      ],
    },
    {
      label: t("settings.groupModel", "模型"),
      items: [
        { id: "model", icon: Cpu, label: t("settings.sectionModel", "对话模型") },
        { id: "media", icon: Film, label: t("settings.sectionMedia", "生成模型") },
        { id: "local", icon: AudioWaveform, label: t("settings.sectionLocal", "本地模型") },
      ],
    },
    {
      label: t("settings.groupAgent", "Agent 能力"),
      items: [
        { id: "browser", icon: Globe, label: t("settings.sectionBrowser", "浏览器控制") },
        { id: "memory", icon: Brain, label: t("settings.sectionMemory", "记忆") },
        { id: "mcp", icon: Blocks, label: t("settings.sectionMcp", "MCP 服务器") },
      ],
    },
    {
      label: t("settings.groupAbout", "关于"),
      items: [{ id: "about", icon: Info, label: t("about.title", "关于") }],
    },
  ];

  const sectionTitles: Record<SettingsSection, string> = {
    basic: t("settings.sectionGeneral", "常规"),
    shortcuts: t("settings.sectionShortcuts", "键盘快捷键"),
    model: t("settings.sectionModel", "对话模型"),
    media: t("settings.sectionMedia", "生成模型"),
    local: t("settings.sectionLocal", "本地模型"),
    browser: t("settings.sectionBrowser", "浏览器控制"),
    memory: t("settings.sectionMemory", "记忆"),
    mcp: t("settings.sectionMcp", "MCP 服务器"),
    about: t("about.title", "关于"),
  };

  // 常规/外观相关/快捷键/意图等即时保存；仅对话模型与生成模型保留保存按钮
  const showSaveBar = section === "model" || section === "media";

  return (
    <div className="sp-page" {...dragRegionProps}>
      <aside className="sp-sidebar" {...dragRegionProps}>
        <div
          role="button"
          tabIndex={0}
          className="sp-back"
          onClick={onBack}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onBack();
            }
          }}
        >
          <ChevronLeft size={14} />
          <span>{t("settings.backToWorkspace", "返回工作区")}</span>
        </div>
        <nav className="sp-nav" aria-label={t("settings.title", "设置")} {...dragRegionProps}>
          {navGroups.map((group) => (
            <div key={group.label} className="sp-nav-group" {...dragRegionProps}>
              <div className="sp-nav-group-label">{group.label}</div>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = section === item.id;
                return (
                  <div
                    key={item.id}
                    role="tab"
                    aria-selected={active}
                    tabIndex={0}
                    className={`sp-nav-item${active ? " active" : ""}`}
                    onClick={() => onSectionChange(item.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSectionChange(item.id);
                      }
                    }}
                  >
                    <Icon size={15} />
                    <span>{item.label}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>
      <div className="sp-main" {...dragRegionProps}>
        <header className="sp-main-header" {...dragRegionProps}>
          <h1 className="sp-title">{sectionTitles[section]}</h1>
          {version && <span className="sp-version">{version}</span>}
        </header>
        <div className="sp-content" {...dragRegionProps}>
          {section === "basic" ? (
            <BasicSection
              themePreference={themePreference}
              onThemeChange={(value: ThemePreference) => setThemePreferenceState(value)}
              onCommit={(body) => void (onSilentSave ?? onSave)(body)}
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
          ) : section === "shortcuts" ? (
            <ShortcutsSection
              globalShortcutEnabled={globalShortcutEnabled}
              onGlobalShortcutChange={handleGlobalShortcutChange}
            />
          ) : section === "browser" ? (
            <BrowserSection />
          ) : section === "media" ? (
            <MediaSection models={mediaModels} onChange={setMediaModels} />
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
        {showSaveBar && (
          <footer className="sp-savebar">
            <Button variant="secondary" onClick={onBack}>
              {t("common.cancel", "取消")}
            </Button>
            <Button variant="primary" onClick={saveCurrentSection}>
              <Save size={15} />
              {t("common.save", "保存")}
            </Button>
          </footer>
        )}
      </div>
    </div>
  );
}
