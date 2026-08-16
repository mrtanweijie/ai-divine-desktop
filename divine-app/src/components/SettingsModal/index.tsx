import { useEffect, useState } from "react";
import { Cpu, Info, Save, Settings2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import tauriConfig from "../../../src-tauri/tauri.conf.json";
import type { Settings } from "@/types";
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
import "./index.less";

interface SettingsModalProps {
  settings: Settings;
  onClose: () => void;
  onSave: (
    body: Partial<Settings> & { api_key?: string; glm_api_key?: string }
  ) => Promise<void> | void;
}

export function SettingsModal({
  settings,
  onClose,
  onSave,
}: SettingsModalProps) {
  const { t } = useTranslation();
  const [locale, setLocaleState] = useState<AppLocale>(readLocalePreference);
  const [model, setModel] = useState(settings.model);
  const [baseUrl, setBaseUrl] = useState(settings.base_url);
  const [apiKey, setApiKey] = useState("");
  const [glmApiKey, setGlmApiKey] = useState("");
  const [username, setUsername] = useState(settings.username);
  const [effort, setEffort] = useState(
    settings.think_default ? settings.reasoning_effort ?? "high" : "off"
  );
  const [contextLimit, setContextLimit] = useState(settings.context_limit);
  const [provider, setProvider] = useState(settings.provider);
  const [showKey, setShowKey] = useState(false);
  const [showGlmKey, setShowGlmKey] = useState(false);
  const [version, setVersion] = useState(`v${tauriConfig.version}`);
  const [themePreference, setThemePreferenceState] = useThemePreference();
  const [section, setSection] = useState<"basic" | "model" | "about">("basic");

  useEffect(() => {
    setSettingsOpen(true);
    return () => setSettingsOpen(false);
  }, []);

  useEffect(() => {
    setModel(settings.model);
    setBaseUrl(settings.base_url);
    setUsername(settings.username);
    setEffort(
      settings.think_default ? settings.reasoning_effort ?? "high" : "off"
    );
    setContextLimit(settings.context_limit);
    setProvider(settings.provider);
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
      const body: Partial<Settings> & {
        api_key?: string;
        glm_api_key?: string;
      } = {
        provider,
        model,
        base_url: baseUrl,
      };
      const trimmedKey = apiKey.trim();
      if (trimmedKey) body.api_key = trimmedKey;
      const trimmedGlmKey = glmApiKey.trim();
      if (trimmedGlmKey) body.glm_api_key = trimmedGlmKey;
      void onSave(body);
    }
  };

  return (
    <Modal
      open
      title={t("settings.title", "设置")}
      titleSuffix={version}
      onClose={onClose}
      width={720}
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
              provider={provider}
              onProviderChange={setProvider}
              model={model}
              onModelChange={setModel}
              baseUrl={baseUrl}
              onBaseUrlChange={setBaseUrl}
              apiKey={apiKey}
              onApiKeyChange={setApiKey}
              showKey={showKey}
              onToggleShowKey={() => setShowKey((value) => !value)}
              glmApiKey={glmApiKey}
              onGlmApiKeyChange={setGlmApiKey}
              showGlmKey={showGlmKey}
              onToggleShowGlmKey={() => setShowGlmKey((value) => !value)}
              hasApiKey={settings.has_api_key}
              hasGlmKey={settings.has_glm_key}
            />
          ) : (
            <AboutSection />
          )}
        </div>
      </div>
    </Modal>
  );
}
