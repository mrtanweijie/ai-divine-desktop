// Local LLM settings section for the settings modal.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AudioWaveform, ChevronDown, Infinity, Zap } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { Tag } from "@/components/ui/Tag";
import { request } from "@/services/request";
import type { DownloadProgress, LocalLLMStatus } from "@/types";

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
  const [progress, setProgress] = useState<Record<string, DownloadProgress>>({});
  // 推荐模型列表：默认收起，点击卡片展开详情（与"模型"tab 交互一致）
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    void loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      const s = await request<LocalLLMStatus>("/local_llm/status");
      setStatus(s);
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
      await loadStatus();
    } catch (e) {
      console.error("Install failed:", e);
    } finally {
      setInstalling(null);
      setProgress((prev) => {
        const next = { ...prev };
        delete next[modelId];
        return next;
      });
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
  const activeModel = status?.active_model;

  return (
    <div className="settings-section">
      <h3>{t("settings.localLLM", "意图识别模式")}</h3>

      {/* 启动失败提示 */}
      {status?.last_error && (
        <div className="local-llm-error">
          <strong>{t("settings.localLLMStartFailed", "本地模型启动失败")}:</strong>{" "}
          {status.last_error}
        </div>
      )}

      {/* 选了本地模式但模型未运行 */}
      {(localLLMMode === "local" || localLLMMode === "hybrid") &&
        status &&
        !status.running && (
          <div className="local-llm-hint">
            {t(
              "settings.localLLMNotRunning",
              "本地模型未运行，意图识别将回退到关键词/云端，启动模型后生效"
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
          {recommended.map((model) => {
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
                  <button
                    type="button"
                    className="settings-model-summary"
                    onClick={toggle}
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
                    {isInstalled && !isActive && (
                      <Tag>{t("settings.installedBadge", "已安装")}</Tag>
                    )}
                  </button>
                  <button
                    type="button"
                    className={`settings-model-chevron${expanded ? " open" : ""}`}
                    onClick={toggle}
                    aria-label={
                      expanded
                        ? t("settings.collapseModel", "收起")
                        : t("settings.expandModel", "展开详情")
                    }
                  >
                    <ChevronDown size={14} />
                  </button>
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
                      {isInstalling ? (
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
                      ) : isInstalled ? (
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
                          onClick={() => handleInstall(model.id)}
                          disabled={loading}
                        >
                          {t("settings.install", "一键安装")}
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {recommended.length === 0 && (
            <div className="empty-state">
              {t("settings.noRecommendedModels", "暂无推荐模型，请检查硬件配置")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
