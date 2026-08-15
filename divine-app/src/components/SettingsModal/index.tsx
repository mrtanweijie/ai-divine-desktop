import { useEffect, useState } from "react";
import { Cpu, Info, Save, Settings2 } from "lucide-react";
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
  const [thinkDefault, setThinkDefault] = useState(settings.think_default);
  const [reasoningEffort, setReasoningEffort] = useState(
    settings.reasoning_effort ?? "high"
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
    setThinkDefault(settings.think_default);
    setReasoningEffort(settings.reasoning_effort ?? "high");
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

  return (
    <Modal
      open
      title={t("settings.title", "设置")}
      titleSuffix={version}
      onClose={onClose}
      width={720}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel", "取消")}
          </Button>
          <Button
            variant="primary"
            onClick={() =>
              onSave({
                provider,
                model,
                base_url: baseUrl,
                api_key: apiKey,
                glm_api_key: glmApiKey,
                username,
                think_default: thinkDefault,
                reasoning_effort: reasoningEffort,
                context_limit: contextLimit,
              })
            }
          >
            <Save size={15} />
            {t("common.save", "保存")}
          </Button>
        </>
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
              thinkDefault={thinkDefault}
              onThinkDefaultChange={setThinkDefault}
              reasoningEffort={reasoningEffort}
              onReasoningEffortChange={setReasoningEffort}
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
