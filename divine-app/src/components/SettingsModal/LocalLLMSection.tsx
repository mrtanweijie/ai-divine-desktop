// Local LLM settings section for the settings modal.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AudioWaveform, ChevronDown, Infinity, Zap } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { Tag } from "@/components/ui/Tag";
import { toast } from "@/components/ui/Toast";
import { request } from "@/services/request";
import { isTauri } from "@/services/tauri";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import type {
  DownloadProgress,
  LocalLLMStatus,
  RecommendedModel,
} from "@/types";

// 模型描述：后端 registry 返回中文原文，这里按模型 id 映射到 i18n 词条；
// 未知模型（如用户自装）回退后端原文。
const MODEL_DESC_KEYS: Record<string, string> = {
  "qwen2.5-0.5b-instruct-q4km": "localModel.descQwen25_0_5b",
  "qwen2.5-1.5b-instruct-q4km": "localModel.descQwen25_1_5b",
  "qwen2.5-3b-instruct-q4km": "localModel.descQwen25_3b",
  "phi-3-mini-4k-q4km": "localModel.descPhi3Mini4k",
  "gemma-2-2b-it-q4km": "localModel.descGemma2_2b",
};

interface LocalLLMSectionProps {
  localLLMEnabled: boolean;
  localLLMMode: "keyword" | "local" | "hybrid";
  onModeChange: (mode: "keyword" | "local" | "hybrid") => void;
}

export function LocalLLMSection({
  localLLMEnabled: _localLLMEnabled,
  localLLMMode,
  onModeChange,
}: LocalLLMSectionProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<LocalLLMStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [installing, setInstalling] = useState<string | null>(null);
  const [customInstallingKey, setCustomInstallingKey] = useState<string | null>(null);
  const [customUrl, setCustomUrl] = useState("");
  const [progress, setProgress] = useState<Record<string, DownloadProgress>>({});
  // 记录上一轮轮询进度，用于检测"条目消失 = 下载完成"
  const lastProgressRef = useRef<Record<string, DownloadProgress>>({});
  // 推荐模型列表：默认收起，点击卡片展开详情（与"模型"tab 交互一致）
  const [expandedId, setExpandedId] = useState<string | null>(null);
  // 自定义模型安装表单
  const [customOpen, setCustomOpen] = useState(false);
  // 启动失败详情默认收起
  const [errorOpen, setErrorOpen] = useState(false);

  useEffect(() => {
    void loadStatus();
  }, []);

  // 安装中的下载进度轮询（内置/自定义通用）
  useEffect(() => {
    const key = installing ?? customInstallingKey;
    if (!key) return;
    const timer = window.setInterval(async () => {
      try {
        const p = await request<DownloadProgress>(
          `/local_llm/download_progress/${key}`
        );
        setProgress((prev) => ({ ...prev, [key]: p }));
        // 完成检测：之前有总量，现在条目消失（0/0/0）→ 下载完成
        const prev = lastProgressRef.current[key];
        if (prev && prev.total > 0 && p.total === 0 && p.downloaded === 0) {
          lastProgressRef.current[key] = { downloaded: 0, total: 0, percent: 0 };
          setInstalling(null);
          void loadStatus();
          return;
        }
        lastProgressRef.current[key] = p;
      } catch {
        // 忽略瞬时失败，下一轮再试
      }
    }, 500);
    return () => window.clearInterval(timer);
  }, [installing, customInstallingKey]);

  const loadStatus = async () => {
    try {
      const s = await request<LocalLLMStatus>("/local_llm/status");
      setStatus(s);
      // 恢复进行中的下载：后端仍有活动下载（total>0）时恢复进度轮询，
      // 避免"关闭弹窗再打开"只看到"未完成"
      const activeKey = Object.keys(s.download_progress ?? {}).find(
        (k) => (s.download_progress?.[k]?.total ?? 0) > 0
      );
      if (activeKey && !installing && !customInstallingKey) {
        lastProgressRef.current[activeKey] = s.download_progress![activeKey];
        setInstalling(activeKey);
      }
    } catch (e) {
      console.error("Failed to load local LLM status:", e);
    }
  };

  const handleModeChange = async (mode: "keyword" | "local" | "hybrid") => {
    setLoading(true);
    try {
      await request("/local_llm/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      onModeChange(mode);
      await loadStatus();
    } finally {
      setLoading(false);
    }
  };

  const handleInstall = async (modelId: string) => {
    setInstalling(modelId);
    setProgress((prev) => ({ ...prev, [modelId]: { downloaded: 0, total: 0, percent: 0 } }));

    try {
      await request("/local_llm/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId }),
      });
      toast.success(t("settings.installSuccess", "模型安装成功"));
      await loadStatus();
    } catch (e) {
      console.error("Install failed:", e);
      toast.error(t("settings.installFailed", "模型安装失败"));
    } finally {
      setInstalling(null);
      setProgress((prev) => {
        const next = { ...prev };
        delete next[modelId];
        return next;
      });
    }
  };

  const handleInstallCustom = async () => {
    const url = customUrl.trim();
    if (!url) return;
    const key = `custom-${Date.now()}`;
    setCustomInstallingKey(key);
    setProgress((prev) => ({ ...prev, [key]: { downloaded: 0, total: 0, percent: 0 } }));
    try {
      await request("/local_llm/install_custom", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, key }),
      });
      setCustomUrl("");
      toast.success(t("settings.installSuccess", "模型安装成功"));
      await loadStatus();
    } catch (e) {
      console.error("Custom install failed:", e);
      toast.error(t("settings.installFailed", "模型安装失败"));
    } finally {
      setCustomInstallingKey(null);
      setProgress((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const handleRegisterLocal = async () => {
    if (!isTauri()) return;
    try {
      const selected = await openDialog({
        multiple: false,
        filters: [{ name: "GGUF", extensions: ["gguf"] }],
      });
      if (!selected || typeof selected !== "string") return;
      setLoading(true);
      try {
        await request("/local_llm/register_local", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: selected }),
        });
        await loadStatus();
      } finally {
        setLoading(false);
      }
    } catch (e) {
      console.error("Register local model failed:", e);
    }
  };

  const handleUninstall = async (modelId: string) => {
    setLoading(true);
    try {
      await request("/local_llm/uninstall", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId }),
      });
      await loadStatus();
    } finally {
      setLoading(false);
    }
  };

  const handleStart = async (modelId: string) => {
    setLoading(true);
    try {
      await request("/local_llm/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId }),
      });
      await loadStatus();
    } catch (e) {
      console.error("Start failed:", e);
      // 启动失败：刷新状态以展示 last_error
      await loadStatus();
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await request("/local_llm/stop", { method: "POST" });
      await loadStatus();
    } finally {
      setLoading(false);
    }
  };

  const formatSize = (gb: number) => {
    if (gb < 1) {
      return `${Math.round(gb * 1024)} MB`;
    }
    return `${gb.toFixed(1)} GB`;
  };

  const recommended = status?.recommended_models ?? [];
  const customModels = status?.custom_models ?? [];
  const activeModel = status?.active_model;

  /** 模型卡片（推荐与自定义共用） */
  const renderModelCard = (model: RecommendedModel) => {
    const isInstalled = model.installed;
    const isInstalling = installing === model.id;
    const isActive = activeModel === model.id;
    const dlProgress = progress[model.id];
    const expanded = expandedId === model.id;
    const toggle = () =>
      setExpandedId((prev) => (prev === model.id ? null : model.id));

    return (
      <div
        key={model.id}
        className={`settings-model-card${
          model.recommended ? " local-model-recommended" : ""
        }${expanded ? " settings-model-card--expanded" : ""}`}
      >
        <div className="settings-model-card-header">
          <div
            role="button"
            tabIndex={0}
            className="settings-model-summary"
            onClick={toggle}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                toggle();
              }
            }}
            aria-expanded={expanded}
            title={
              expanded
                ? t("settings.collapseModel", "收起")
                : t("settings.expandModel", "展开详情")
            }
          >
            <span className="settings-model-name">{model.name}</span>
            {isActive && (
              <Tag tone="success">{t("settings.active", "运行中")}</Tag>
            )}
            {isInstalled && !isActive && !model.incomplete && (
              <Tag>{t("settings.installedBadge", "已安装")}</Tag>
            )}
            {model.incomplete && !isInstalling && (
              <Tag tone="warning">
                {t("settings.incompleteTag", "未完成")}
              </Tag>
            )}
          </div>
          <Button
            variant="icon"
            size="small"
            className={`settings-model-chevron${expanded ? " open" : ""}`}
            onClick={toggle}
            aria-label={
              expanded
                ? t("settings.collapseModel", "收起")
                : t("settings.expandModel", "展开详情")
            }
          >
            <ChevronDown size={14} />
          </Button>
        </div>
        {expanded && (
          <div className="settings-model-card-body">
            <p className="local-model-desc">
              {MODEL_DESC_KEYS[model.id]
                ? t(MODEL_DESC_KEYS[model.id])
                : model.description}
            </p>
            <div className="local-model-meta">
              <span>
                {t("settings.modelSize", "大小")} {formatSize(model.size_gb)}
              </span>
              <span>
                {t("settings.modelRam", "需要内存")}{" "}
                {formatSize(model.required_ram_gb)}
              </span>
              <span>
                {t("settings.modelQuant", "量化")} {model.quantization}
              </span>
              {model.tags.length > 0 && (
                <span className="local-model-tags">
                  {model.tags.join(" / ")}
                </span>
              )}
            </div>
            <div className="model-actions">
              {isInstalling && (
                <div className="install-progress">
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{ width: `${dlProgress?.percent ?? 0}%` }}
                    />
                  </div>
                  <span className="progress-text">
                    {Math.round(dlProgress?.percent ?? 0)}%
                  </span>
                </div>
              )}
              {isInstalled && !model.incomplete ? (
                <Flex gap={8} align="center">
                  {isActive ? (
                    <Button
                      variant="secondary"
                      size="small"
                      onClick={handleStop}
                      disabled={loading}
                    >
                      {t("settings.stop", "停止")}
                    </Button>
                  ) : (
                    <Button
                      variant="primary"
                      size="small"
                      onClick={() => handleStart(model.id)}
                      disabled={loading}
                    >
                      {t("settings.start", "启动")}
                    </Button>
                  )}
                  <Button
                    variant="danger"
                    size="small"
                    onClick={() => handleUninstall(model.id)}
                    disabled={loading || isActive}
                  >
                    {t("settings.uninstall", "卸载")}
                  </Button>
                </Flex>
              ) : (
                <Button
                  variant="primary"
                  size="small"
                  className="local-model-install-btn"
                  onClick={() => handleInstall(model.id)}
                  disabled={loading || isInstalling}
                  loading={isInstalling}
                >
                  {t("settings.install", model.incomplete ? "重新安装" : "一键安装")}
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="settings-section">
      <h3 className="local-llm-title">
        {t("settings.localLLM", "意图识别模式")}
        {/* 占位容器常驻（local/hybrid 模式），固定尺寸避免 Tag 出现/
            消失导致标题行高度变化引发页面抖动 */}
        {(localLLMMode === "local" || localLLMMode === "hybrid") &&
          status && (
            <span className="local-llm-title-tag">
              {!status.running && (
                <Tag tone="warning">
                  {t("settings.notStartedTag", "未启动")}
                </Tag>
              )}
            </span>
          )}
      </h3>

      {/* 启动失败提示：默认收起，点击展开 */}
      {status?.last_error && (
        <div
          className={`local-llm-error${errorOpen ? " open" : ""}`}
          onClick={() => setErrorOpen((prev) => !prev)}
          role="button"
          tabIndex={0}
        >
          <div className="local-llm-error-header">
            <strong>
              {t("settings.localLLMStartFailed", "本地模型启动失败")}
            </strong>
            <ChevronDown size={12} className="local-llm-error-chevron" />
          </div>
          {errorOpen && (
            <div className="local-llm-error-body">{status.last_error}</div>
          )}
        </div>
      )}

      {/* 意图识别模式 */}
      <div className="settings-field">
        <div className="mode-cards">
          <div
            className={`mode-card ${localLLMMode === "keyword" ? "active" : ""}`}
            onClick={() => !loading && handleModeChange("keyword")}
          >
            <div className="mode-card-icon">
              <Zap size={24} />
            </div>
            <div className="mode-card-title">
              {t("settings.modeKeywordTitle", "关键词匹配")}
            </div>
            <div className="mode-card-desc">
              {t("settings.modeKeywordDesc", "最快，基于规则匹配")}
            </div>
          </div>
          <div
            className={`mode-card ${localLLMMode === "local" ? "active" : ""}`}
            onClick={() => !loading && handleModeChange("local")}
          >
            <div className="mode-card-icon">
              <Infinity size={24} />
            </div>
            <div className="mode-card-title">
              {t("settings.modeLocalTitle", "本地模型")}
            </div>
            <div className="mode-card-desc">
              {t("settings.modeLocalDesc", "更智能，AI 理解意图")}
            </div>
          </div>
          <div
            className={`mode-card ${localLLMMode === "hybrid" ? "active" : ""}`}
            onClick={() => !loading && handleModeChange("hybrid")}
          >
            <div className="mode-card-icon">
              <AudioWaveform size={24} />
            </div>
            <div className="mode-card-title">
              {t("settings.modeHybridTitle", "混合模式")}
            </div>
            <div className="mode-card-desc">
              {t("settings.modeHybridDesc", "关键词 + AI 双重判断")}
            </div>
          </div>
        </div>
      </div>

      {/* 推荐模型 */}
      <div className="settings-field">
        <label>{t("settings.recommendedModels", "推荐模型")}</label>
        <div className="model-list">
          {recommended.map((model) => renderModelCard(model))}
          {customModels.map((model) => renderModelCard(model))}

          {recommended.length === 0 && customModels.length === 0 && (
            <div className="empty-state">
              {t("settings.noRecommendedModels", "暂无推荐模型，请检查硬件配置")}
            </div>
          )}

          {/* 自定义模型：点击展开安装表单 */}
          <div
            className={`settings-model-card local-model-custom-card${
              customOpen ? " settings-model-card--expanded" : ""
            }`}
          >
            <div className="settings-model-card-header">
              <div
                role="button"
                tabIndex={0}
                className="settings-model-summary"
                onClick={() => setCustomOpen((prev) => !prev)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setCustomOpen((prev) => !prev);
                  }
                }}
                aria-expanded={customOpen}
              >
                <span className="settings-model-name">
                  {t("settings.customInstall", "自定义模型")}
                </span>
              </div>
              <Button
                variant="icon"
                size="small"
                className={`settings-model-chevron${customOpen ? " open" : ""}`}
                onClick={() => setCustomOpen((prev) => !prev)}
                aria-label={
                  customOpen
                    ? t("settings.collapseModel", "收起")
                    : t("settings.expandModel", "展开")
                }
              >
                <ChevronDown size={14} />
              </Button>
            </div>
            {customOpen && (
              <div className="settings-model-card-body">
                <Input
                  className="local-model-url"
                  type="text"
                  value={customUrl}
                  onChange={(event) => setCustomUrl(event.target.value)}
                  placeholder={t(
                    "settings.customInstallUrlPlaceholder",
                    "粘贴 GGUF 下载链接（如 HuggingFace resolve 直链）"
                  )}
                  disabled={loading || customInstallingKey !== null}
                  action={
                    <Button
                      variant="primary"
                      size="small"
                      className="local-model-install-btn"
                      onClick={handleInstallCustom}
                      disabled={
                        loading ||
                        customInstallingKey !== null ||
                        !customUrl.trim()
                      }
                      loading={customInstallingKey !== null}
                    >
                      {t("settings.install", "安装")}
                    </Button>
                  }
                />
                <Flex justify="space-between" align="center" gap={8} wrap>
                  {customInstallingKey ? (
                    <div className="install-progress">
                      <div className="progress-bar">
                        <div
                          className="progress-fill"
                          style={{
                            width: `${progress[customInstallingKey]?.percent ?? 0}%`,
                          }}
                        />
                      </div>
                      <span className="progress-text">
                        {Math.round(progress[customInstallingKey]?.percent ?? 0)}%
                      </span>
                    </div>
                  ) : (
                    <span />
                  )}
                  {isTauri() && (
                    <Button
                      variant="ghost"
                      size="small"
                      onClick={handleRegisterLocal}
                      disabled={loading || customInstallingKey !== null}
                    >
                      {t("settings.registerLocal", "选择本地 .gguf 文件")}
                    </Button>
                  )}
                </Flex>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
