import { useEffect, useState } from "react";
import { Cpu, Eye, EyeOff, Save, Settings2 } from "lucide-react";
import tauriConfig from "../../../src-tauri/tauri.conf.json";
import type { Settings } from "@/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { getAppVersion } from "@/services/tauri";
import {
  useThemePreference,
  type ThemePreference,
} from "@/services/theme";
import "./index.less";

const MODEL_OPTIONS = [
  { value: "deepseek-v4-flash", label: "deepseek-v4-flash" },
  { value: "deepseek-v4-pro", label: "deepseek-v4-pro" },
];

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
  const [model, setModel] = useState(settings.model);
  const [baseUrl, setBaseUrl] = useState(settings.base_url);
  const [apiKey, setApiKey] = useState("");
  const [glmApiKey, setGlmApiKey] = useState("");
  const [username, setUsername] = useState(settings.username);
  const [thinkDefault, setThinkDefault] = useState(settings.think_default);
  const [contextLimit, setContextLimit] = useState(settings.context_limit);
  const [provider, setProvider] = useState(settings.provider);
  const [showKey, setShowKey] = useState(false);
  const [showGlmKey, setShowGlmKey] = useState(false);
  const [version, setVersion] = useState(`v${tauriConfig.version}`);
  const [themePreference, setThemePreferenceState] = useThemePreference();
  const [section, setSection] = useState<"basic" | "model">("basic");

  useEffect(() => {
    setModel(settings.model);
    setBaseUrl(settings.base_url);
    setUsername(settings.username);
    setThinkDefault(settings.think_default);
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
      title="设置"
      titleSuffix={version}
      onClose={onClose}
      width={700}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            取消
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
                context_limit: contextLimit,
              })
            }
          >
            <Save size={15} />
            保存
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
            <span>通用</span>
          </button>
          <button
            type="button"
            className={`settings-nav-item${
              section === "model" ? " active" : ""
            }`}
            onClick={() => setSection("model")}
          >
            <Cpu size={15} />
            <span>模型</span>
          </button>
        </div>
        <div className="settings-main">
          {section === "basic" ? (
            <div className="settings-form">
              <Select
                label="主题"
                value={themePreference}
                onChange={(value) =>
                  setThemePreferenceState(value as ThemePreference)
                }
                options={[
                  { value: "dark", label: "深色" },
                  { value: "light", label: "浅色" },
                  { value: "system", label: "跟随系统" },
                ]}
              />
              <Input
                label="用户名"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="用户"
              />
              <Input
                label="上下文保留条数"
                type="text"
                inputMode="numeric"
                value={contextLimit}
                onChange={(event) => {
                  const digits = event.target.value.replace(/\D/g, "");
                  setContextLimit(
                    digits === "" ? 1 : Math.min(200, Number(digits))
                  );
                }}
              />
              <div className="ui-field">
                <span className="ui-field-label">默认深度思考</span>
                <Switch checked={thinkDefault} onChange={setThinkDefault} />
              </div>
            </div>
          ) : (
            <div className="settings-form">
              <Select
                label="Provider"
                value={provider}
                onChange={setProvider}
                options={[
                  { value: "auto", label: "自动（有 Key 用 DeepSeek）" },
                  { value: "langchain", label: "DeepSeek（ChatDeepSeek）" },
                  { value: "mock", label: "本地演示" },
                ]}
              />
              <Select
                label="模型"
                value={model}
                onChange={setModel}
                editable
                options={MODEL_OPTIONS}
                placeholder="deepseek-v4-flash"
              />
              <Input
                label="Base URL"
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder="https://api.deepseek.com"
              />
              <Input
                label={`API Key${settings.has_api_key ? "（已保存）" : ""}`}
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="sk-..."
                autoComplete="off"
                action={
                  <Button
                    variant="icon"
                    size="small"
                    onClick={() => setShowKey((value) => !value)}
                    aria-label={showKey ? "隐藏 API Key" : "显示 API Key"}
                  >
                    {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                  </Button>
                }
              />
              <Input
                label={`GLM API Key（识图能力支持）${
                  settings.has_glm_key ? "（已保存）" : ""
                }`}
                type={showGlmKey ? "text" : "password"}
                value={glmApiKey}
                onChange={(event) => setGlmApiKey(event.target.value)}
                placeholder="glm key..."
                autoComplete="off"
                action={
                  <Button
                    variant="icon"
                    size="small"
                    onClick={() => setShowGlmKey((value) => !value)}
                    aria-label={
                      showGlmKey ? "隐藏 GLM API Key" : "显示 GLM API Key"
                    }
                  >
                    {showGlmKey ? <EyeOff size={14} /> : <Eye size={14} />}
                  </Button>
                }
              />
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
