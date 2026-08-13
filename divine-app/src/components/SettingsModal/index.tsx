import { useEffect, useState } from "react";
import { Eye, EyeOff, Save } from "lucide-react";
import tauriConfig from "../../../src-tauri/tauri.conf.json";
import type { Settings } from "@/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { getAppVersion } from "@/services/tauri";
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
      width={520}
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
        <Input
          label="用户名"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="用户"
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
              aria-label={showGlmKey ? "隐藏 GLM API Key" : "显示 GLM API Key"}
            >
              {showGlmKey ? <EyeOff size={14} /> : <Eye size={14} />}
            </Button>
          }
        />
        <div className="field-row">
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
        </div>
        <div className="ui-field">
          <span className="ui-field-label">默认深度思考</span>
          <Switch checked={thinkDefault} onChange={setThinkDefault} />
        </div>
      </div>
    </Modal>
  );
}
