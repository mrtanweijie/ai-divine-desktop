import { ChevronDown, Eye, EyeOff, MoreHorizontal, Plus, Star, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { getBalance, type BalanceInfo } from "@/services/api";
import type { ModelConfig } from "@/types";

const MODEL_OPTIONS = [
  { value: "deepseek-v4-flash", label: "deepseek-v4-flash" },
  { value: "deepseek-v4-flash-vision-exp", label: "deepseek-v4-flash-vision-exp" },
  { value: "deepseek-v4-pro", label: "deepseek-v4-pro" },
];

interface SettingsModelSectionProps {
  models: ModelConfig[];
  onModelsChange: (models: ModelConfig[]) => void;
  modelKeys: Record<string, string>;
  onModelKeyChange: (id: string, value: string) => void;
  showKeys: Record<string, boolean>;
  onToggleShowKey: (id: string) => void;
  glmApiKey: string;
  onGlmApiKeyChange: (value: string) => void;
  showGlmKey: boolean;
  onToggleShowGlmKey: () => void;
  hasGlmKey: boolean;
  /** 弹窗确认删除；未提供时直接删除 */
  onConfirm?: (title: string, description: string, action: () => void) => void;
  /** 设为默认后自动保存 */
  onAutoSave?: (models: ModelConfig[]) => void;
}

export function ModelSection({
  models,
  onModelsChange,
  modelKeys,
  onModelKeyChange,
  showKeys,
  onToggleShowKey,
  glmApiKey,
  onGlmApiKeyChange,
  showGlmKey,
  onToggleShowGlmKey,
  hasGlmKey,
  onConfirm,
  onAutoSave,
}: SettingsModelSectionProps) {
  const { t } = useTranslation();
  // 列表默认收起，仅展示模型名；点击卡片展开编辑。只有一个模型时默认展开。
  const [expandedId, setExpandedId] = useState<string | null>(() =>
    models.length === 1 ? (models[0]?.id ?? null) : null
  );
  // 余额信息（DeepSeek 端点可用）
  const [balances, setBalances] = useState<Record<string, BalanceInfo>>({});

  // 为有 key 的 DeepSeek 模型批量查询余额
  useEffect(() => {
    let cancelled = false;
    const targets = models.filter(
      (m) => m.has_api_key && /deepseek/i.test(m.base_url)
    );
    if (targets.length === 0) return;
    Promise.all(
      targets.map(async (m) => {
        try {
          const info = await getBalance(m.id);
          return [m.id, info] as const;
        } catch {
          return [m.id, { available: false }] as const;
        }
      })
    ).then((results) => {
      if (cancelled) return;
      const next: Record<string, BalanceInfo> = {};
      for (const [id, info] of results) next[id] = info;
      setBalances(next);
    });
    return () => {
      cancelled = true;
    };
  }, [models]);

  const updateModel = (id: string, patch: Partial<ModelConfig>) => {
    onModelsChange(
      models.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry))
    );
  };

  const handleModelChange = (id: string, value: string) => {
    // 名称跟随模型名自动同步，模型名同时作为展示名与模型标识。
    updateModel(id, { model: value, name: value });
  };

  const addModel = () => {
    const entry: ModelConfig = {
      id: `model-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      // 模型名留空，不默认选择 deepseek-v4-flash，由用户自行选择或输入
      name: "",
      provider: "langchain",
      model: "",
      base_url: "https://api.deepseek.com",
      has_api_key: false,
      // 新添加的模型不自动设为默认，保持当前默认模型不变
      active: false,
    };
    onModelsChange([...models, entry]);
    // 新添加的模型直接展开，方便立即填写
    setExpandedId(entry.id);
  };

  const removeModel = (id: string) => {
    const remaining = models.filter((entry) => entry.id !== id);
    if (remaining.length === 0) return;
    if (models.find((entry) => entry.id === id)?.active) {
      remaining[0] = { ...remaining[0], active: true };
    }
    onModelsChange(remaining);
    setExpandedId((prev) =>
      prev === id ? (remaining.length === 1 ? remaining[0].id : null) : prev
    );
  };

  const setActive = (id: string) => {
    const newModels = models.map((entry) => ({
      ...entry,
      active: entry.id === id,
    }));
    onModelsChange(newModels);
    onAutoSave?.(newModels);
  };

  const toggleExpanded = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  return (
    <div className="settings-form">
      <p className="settings-field-hint-inline settings-models-hint">
        {t("settings.modelsHint", "可配置多个模型，对话时在输入框发送按钮左侧快速切换")}
      </p>
      <div className="settings-model-list">
        {models.map((entry) => {
          const expanded = expandedId === entry.id;
          return (
          <div
            key={entry.id}
            className={`settings-model-card${
              entry.active ? " settings-model-card--active" : ""
            }${expanded ? " settings-model-card--expanded" : ""}`}
          >
            <div className="settings-model-card-header">
              <button
                type="button"
                className="settings-model-summary"
                onClick={() => toggleExpanded(entry.id)}
                aria-expanded={expanded}
                title={expanded ? t("settings.collapseModel", "收起") : t("settings.expandModel", "展开编辑")}
              >
                <span className="settings-model-name">
                  {entry.name ||
                    entry.model ||
                    t("settings.modelUnnamed", "未命名模型")}
                </span>
                {entry.active && (
                  <span className="settings-model-badge">
                    <Star size={10} fill="currentColor" />
                    {t("settings.defaultBadge", "默认")}
                  </span>
                )}
                {balances[entry.id]?.available && (
                  <span className="settings-model-balance">
                    ¥{balances[entry.id].balance}
                  </span>
                )}
              </button>
              {models.length > 1 && (
                <Dropdown
                  align="end"
                  direction="below"
                  label={t("settings.modelActions", "模型操作")}
                  openOn="hover"
                  trigger={
                    <Button
                      variant="icon"
                      size="small"
                      className="settings-model-more"
                      aria-label={t("settings.modelActions", "模型操作")}
                      title={t("settings.modelActions", "模型操作")}
                    >
                      <MoreHorizontal size={16} />
                    </Button>
                  }
                  items={[
                    {
                      key: "active",
                      icon: (
                        <Star
                          size={12}
                          fill={entry.active ? "currentColor" : "none"}
                          color={
                            entry.active ? "var(--color-accent)" : undefined
                          }
                        />
                      ),
                      label: entry.active
                        ? t("settings.defaultModelLabel", "默认模型")
                        : t("settings.setActiveModel", "设为默认"),
                      onClick: () => setActive(entry.id),
                    },
                    {
                      key: "delete",
                      icon: <Trash2 size={12} />,
                      label: t("settings.deleteModel", "删除模型"),
                      description:
                        /deepseek/i.test(entry.base_url)
                          ? t("settings.baseModelNoDelete", "基础模型不可删除")
                          : undefined,
                      // DeepSeek 作为基础模型不可删除，仅剩一个模型时也不可删除
                      disabled:
                        models.length <= 1 ||
                        /deepseek/i.test(entry.base_url),
                      onClick: () => {
                        const modelLabel =
                          entry.name ||
                          entry.model ||
                          t("settings.modelUnnamed", "未命名模型");
                        const doRemove = () => removeModel(entry.id);
                        if (onConfirm) {
                          onConfirm(
                            t("settings.deleteModelConfirmTitle", "删除模型"),
                            t(
                              "settings.deleteModelConfirmMessage",
                              "确定删除模型「{{name}}」吗？点击「保存」后生效。",
                              { name: modelLabel }
                            ),
                            doRemove
                          );
                        } else {
                          doRemove();
                        }
                      },
                    },
                  ]}
                />
              )}
              <button
                type="button"
                className={`settings-model-chevron${
                  expanded ? " open" : ""
                }`}
                onClick={() => toggleExpanded(entry.id)}
                aria-label={
                  expanded
                    ? t("settings.collapseModel", "收起")
                    : t("settings.expandModel", "展开编辑")
                }
              >
                <ChevronDown size={14} />
              </button>
            </div>
            {expanded && (
              <div className="settings-model-card-body">
                <Select
                  label={t("settings.model", "模型")}
                  value={entry.model}
                  onChange={(value) => handleModelChange(entry.id, value)}
                  editable
                  options={MODEL_OPTIONS}
                  placeholder="deepseek-v4-flash"
                />
                <Input
                  label="Base URL"
                  value={entry.base_url}
                  onChange={(event) =>
                    updateModel(entry.id, { base_url: event.target.value })
                  }
                  placeholder="https://api.deepseek.com"
                />
                <Input
                  label={t("settings.apiKeyLabel", "API Key{{saved}}", {
                    saved: entry.has_api_key
                      ? t("settings.saved", "（已保存）")
                      : "",
                  })}
                  type={showKeys[entry.id] ? "text" : "password"}
                  value={modelKeys[entry.id] ?? ""}
                  onChange={(event) =>
                    onModelKeyChange(entry.id, event.target.value)
                  }
                  placeholder="sk-..."
                  autoComplete="off"
                  action={
                    <Button
                      variant="icon"
                      size="small"
                      onClick={() => onToggleShowKey(entry.id)}
                      aria-label={
                        showKeys[entry.id]
                          ? t("settings.hideApiKey", "隐藏 API Key")
                          : t("settings.showApiKey", "显示 API Key")
                      }
                    >
                      {showKeys[entry.id] ? (
                        <EyeOff size={14} />
                      ) : (
                        <Eye size={14} />
                      )}
                    </Button>
                  }
                />
              </div>
            )}
          </div>
        );
        })}
      </div>
      <Button variant="secondary" className="settings-model-add" onClick={addModel}>
        <Plus size={14} />
        {t("settings.addModel", "添加模型")}
      </Button>
      <Input
        label={t("settings.glmApiKeyLabel", "GLM API Key（识图能力支持）{{saved}}", {
          saved: hasGlmKey ? t("settings.saved", "（已保存）") : "",
        })}
        type={showGlmKey ? "text" : "password"}
        value={glmApiKey}
        onChange={(event) => onGlmApiKeyChange(event.target.value)}
        placeholder="glm key..."
        autoComplete="off"
        action={
          <Button
            variant="icon"
            size="small"
            onClick={onToggleShowGlmKey}
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
  );
}
