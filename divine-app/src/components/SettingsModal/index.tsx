import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Cpu,
  Download,
  Eye,
  EyeOff,
  Info,
  RefreshCw,
  Save,
  Settings2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import tauriConfig from "../../../src-tauri/tauri.conf.json";
import type { Settings } from "@/types";
import {
  readLocalePreference,
  setLocale,
  type AppLocale,
} from "@/i18n";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { toast } from "@/components/ui/Toast";
import { getAppVersion, openUrl } from "@/services/tauri";
import {
  checkForUpdates,
  downloadAndInstallUpdate,
  setSettingsOpen,
  useUpdaterState,
} from "@/services/updater";
import {
  useThemePreference,
  type ThemePreference,
} from "@/services/theme";
import { copyText } from "@/utils";
import "./index.less";

const MODEL_OPTIONS = [
  { value: "deepseek-v4-flash", label: "deepseek-v4-flash" },
  { value: "deepseek-v4-pro", label: "deepseek-v4-pro" },
];

function GithubIcon({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}

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
  const [contextLimit, setContextLimit] = useState(settings.context_limit);
  const [provider, setProvider] = useState(settings.provider);
  const [showKey, setShowKey] = useState(false);
  const [showGlmKey, setShowGlmKey] = useState(false);
  const [version, setVersion] = useState(`v${tauriConfig.version}`);
  const [themePreference, setThemePreferenceState] = useThemePreference();
  const [section, setSection] = useState<"basic" | "model" | "about">("basic");
  const updater = useUpdaterState();

  useEffect(() => {
    setSettingsOpen(true);
    return () => setSettingsOpen(false);
  }, []);

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
            <div className="settings-form">
              <Select
                label={t("settings.theme", "主题")}
                value={themePreference}
                onChange={(value) =>
                  setThemePreferenceState(value as ThemePreference)
                }
                options={[
                  { value: "dark", label: t("settings.themeDark", "深色") },
                  { value: "light", label: t("settings.themeLight", "浅色") },
                  { value: "system", label: t("settings.themeSystem", "跟随系统") },
                ]}
              />
              <Select
                label={t("settings.language", "语言")}
                value={locale}
                onChange={(value) => {
                  const next = value as AppLocale;
                  setLocaleState(next);
                  setLocale(next);
                }}
                options={[
                  { value: "zh-CN", label: "简体中文" },
                  { value: "zh-TW", label: "繁體中文" },
                  { value: "en", label: "English" },
                ]}
              />
              <Input
                label={t("settings.username", "用户名")}
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder={t("settings.usernamePlaceholder", "用户")}
              />
              <Input
                label={t("settings.contextLimit", "上下文保留条数")}
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
                <span className="ui-field-label">
                  {t("settings.thinkDefault", "默认深度思考")}
                </span>
                <Switch checked={thinkDefault} onChange={setThinkDefault} />
              </div>
              <div className="settings-updater">
                <span className="ui-field-label">
                  {t("updater.title", "软件更新")}
                </span>
                <div className="settings-updater-actions">
                  {(updater.status === "idle" ||
                    updater.status === "uptodate" ||
                    updater.status === "error" ||
                    updater.status === "checking") && (
                    <Button
                      variant="secondary"
                      size="small"
                      loading={updater.status === "checking"}
                      onClick={() => void checkForUpdates()}
                    >
                      {updater.status === "error"
                        ? t("updater.retry", "重试")
                        : updater.status === "checking"
                          ? t("updater.checking", "检查中...")
                          : t("updater.check", "检查更新")}
                    </Button>
                  )}
                  {updater.status === "available" && (
                    <Button
                      variant="primary"
                      size="small"
                      onClick={() => void downloadAndInstallUpdate()}
                    >
                      {t("updater.downloadAndRestart", "下载并重启")}
                    </Button>
                  )}
                  {updater.status !== "idle" &&
                    updater.status !== "checking" && (
                      <span
                        className={`settings-updater-status settings-updater-status--${updater.status}`}
                      >
                        {updater.status === "available" && (
                          <>
                            <Download size={14} />
                            <span>
                              {t("updater.available", "发现新版本 v{{version}}", {
                                version: updater.version,
                              })}
                            </span>
                          </>
                        )}
                        {updater.status === "downloading" && (
                          <>
                            <RefreshCw size={14} />
                            <span>
                              {t(
                                "updater.downloading",
                                "正在下载 v{{version}} {{progress}}%",
                                {
                                  version: updater.version,
                                  progress: updater.progress,
                                }
                              )}
                            </span>
                          </>
                        )}
                        {updater.status === "downloaded" && (
                          <>
                            <RefreshCw size={14} />
                            <span>
                              {t("updater.restarting", "更新完成，正在重启...")}
                            </span>
                          </>
                        )}
                        {updater.status === "uptodate" && (
                          <span>{t("updater.uptodate", "已是最新版本")}</span>
                        )}
                        {updater.status === "error" && (
                          <span className="settings-updater-error">
                            <AlertTriangle size={13} />
                            {t("updater.checkFailed", "检查更新失败，请稍后重试")}
                          </span>
                        )}
                        {updater.status === "disabled" && (
                          <span>
                            {t("updater.disabled", "当前环境不支持自动更新")}
                          </span>
                        )}
                      </span>
                    )}
                </div>
              </div>
            </div>
          ) : section === "model" ? (
            <div className="settings-form">
              <Select
                label="Provider"
                value={provider}
                onChange={setProvider}
                options={[
                  { value: "auto", label: t("settings.providerAuto", "自动（有 Key 用 DeepSeek）") },
                  { value: "langchain", label: t("settings.providerLangchain", "DeepSeek（ChatDeepSeek）") },
                  { value: "mock", label: t("settings.providerMock", "本地演示") },
                ]}
              />
              <Select
                label={t("settings.model", "模型")}
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
                label={t("settings.apiKeyLabel", "API Key{{saved}}", {
                  saved: settings.has_api_key
                    ? t("settings.saved", "（已保存）")
                    : "",
                })}
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
                  saved: settings.has_glm_key
                    ? t("settings.saved", "（已保存）")
                    : "",
                })}
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
          ) : (
            <div className="settings-about">
              <section className="settings-about-section">
                <h4>{t("about.sourceLicenseTitle", "开源协议")}</h4>
                <p>
                  <GithubIcon />
                  <button
                    type="button"
                    className="settings-about-link"
                    onClick={() =>
                      void openUrl(
                        "https://github.com/mrtanweijie/ai-divine-desktop"
                      )
                    }
                  >
                    github.com/mrtanweijie/ai-divine-desktop
                  </button>
                </p>
                <p>
                  {t("about.licenseText", "本项目采用 MIT License。")}
                  <button
                    type="button"
                    className="settings-about-link"
                    onClick={() =>
                      void openUrl(
                        "https://github.com/mrtanweijie/ai-divine-desktop/blob/main/LICENSE"
                      )
                    }
                  >
                    MIT License
                  </button>
                </p>
              </section>
              <section className="settings-about-section">
                <h4>{t("about.disclaimerTitle", "免责声明")}</h4>
                <ul>
                  <li>
                    {t(
                      "about.disclaimerAiContent",
                      "AI 生成的内容仅供参考，可能包含错误、过时信息或偏差；重要信息请自行核实，涉及法律、医疗、财务等专业决策请咨询专业人士。"
                    )}
                  </li>
                  <li>
                    {t(
                      "about.disclaimerRisk",
                      "使用本软件处理重要文件或执行高风险操作前，请先备份数据并自行评估风险。"
                    )}
                  </li>
                  <li>
                    {t(
                      "about.disclaimerAsIs",
                      "本项目按“现状”提供，不承诺特定结果，也不保证运行无错误；因使用本软件造成的任何直接或间接损失，由使用者自行承担。"
                    )}
                  </li>
                  <li>
                    {t(
                      "about.disclaimerThirdParty",
                      "调用第三方模型服务时，费用、数据流转、隐私与服务可用性遵循对应服务商的规则。"
                    )}
                  </li>
                  <li>
                    {t(
                      "about.disclaimerPrivacy",
                      "对话、文件和设置默认保存在本机；调用模型服务时，必要的对话上下文会发送给对应服务商。"
                    )}
                  </li>
                </ul>
              </section>
              <section className="settings-about-section">
                <h4>{t("about.contactTitle", "联系方式")}</h4>
                <p>
                  {t("about.contactText", "问题反馈或合作请联系：")}
                  <button
                    type="button"
                    className="settings-about-link"
                    onClick={() => {
                      void copyText("tanweijie@outlook.com").then(() => {
                        toast.success(t("common.copied", "已复制"));
                      });
                    }}
                  >
                    tanweijie@outlook.com
                  </button>
                </p>
              </section>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
