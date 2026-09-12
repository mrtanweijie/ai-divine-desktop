import {
  ChevronDown,
  Eye,
  EyeOff,
  MoreHorizontal,
  Plus,
  Sparkles,
  Star,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Tag } from "@/components/ui/Tag";
import { getBalance, type BalanceInfo } from "@/services/api";
import type { ModelConfig, ToolMode } from "@/types";
import {
  PROVIDER_OPTIONS,
  fetchProviderConfig,
  openProviderConfigDir,
  getEntryProvider,
  getProviderConfig,
} from "@/config/providers";
import "./ModelSection.less";

function toolModeOptions(t: (key: string, fallback: string) => string) {
  return [
    { value: "auto", label: t("settings.toolModeAuto", "自动") },
    { value: "native", label: t("settings.toolModeNative", "原生函数调用") },
    { value: "react", label: t("settings.toolModeReact", "ReAct 文本模式") },
  ];
}

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
  // 打开设置时拉取最新提供商目录（Agent 经 manage_model_providers 改动后无需重启）
  useEffect(() => {
    void fetchProviderConfig();
  }, []);

  const { t } = useTranslation();
  // 列表默认收起，仅展示模型名；点击卡片展开编辑。只有一个模型时默认展开。
  const [expandedId, setExpandedId] = useState<string | null>(() =>
    models.length === 1 ? (models[0]?.id ?? null) : null,
  );
  // 卡片内的"自定义设置"折叠区：默认收起，点击标题展开
  const [customOpen, setCustomOpen] = useState<Record<string, boolean>>({});
  // 余额信息（DeepSeek 端点可用）
  const [balances, setBalances] = useState<Record<string, BalanceInfo>>({});

  const toggleCustomSettings = (id: string) => {
    setCustomOpen((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // 已配置 API Key 的提供方集合：新增模型时下拉过滤掉，避免重复配置
  const vendorsWithKey = new Set<string>(
    models
      .filter((m) => m.has_api_key)
      .map((m) => getEntryProvider(m))
      .filter(Boolean),
  );

  // 提供方下拉选项：过滤掉已配置 Key 的提供方（始终保留"自定义"）
  const availableVendorOptions = PROVIDER_OPTIONS.filter(
    (opt) => opt.value === "custom" || !vendorsWithKey.has(opt.value),
  );

  // 单个条目的下拉选项：过滤后的选项 ∪ 当前条目的提供方（保证已选值可见）
  const vendorOptionsFor = (entry: ModelConfig) => {
    const current = getEntryProvider(entry);
    if (!current) return availableVendorOptions;
    if (availableVendorOptions.some((o) => o.value === current)) {
      return availableVendorOptions;
    }
    const label = PROVIDER_OPTIONS.find((o) => o.value === current)?.label ?? current;
    return [{ value: current, label }, ...availableVendorOptions];
  };

  // 为有 key 的 DeepSeek 模型批量查询余额
  useEffect(() => {
    let cancelled = false;
    const targets = models.filter((m) => m.has_api_key && /deepseek/i.test(m.base_url));
    if (targets.length === 0) return;
    Promise.all(
      targets.map(async (m) => {
        try {
          const info = await getBalance(m.id);
          return [m.id, info] as const;
        } catch {
          return [m.id, { available: false }] as const;
        }
      }),
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
    onModelsChange(models.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry)));
  };

  const handleProviderChange = (id: string, provider: string) => {
    const providerConfig = getProviderConfig(provider);
    updateModel(id, {
      // 持久化用户显式选择的提供方，避免本地模型名（如 qwen2.5:14b）被前缀误判
      vendor: provider,
      model: providerConfig?.default_model || "",
      name: providerConfig?.default_model || "",
      base_url: providerConfig?.base_url || "",
    });
  };

  const addModel = () => {
    const entry: ModelConfig = {
      id: `model-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      // 新增时提供方留空：下拉只展示未配置 Key 的提供方（+ 自定义）
      name: "",
      provider: "langchain",
      model: "",
      base_url: "",
      vendor: "",
      has_api_key: false,
      active: false,
      tool_mode: "auto",
    };
    onModelsChange([...models, entry]);
    setExpandedId(entry.id);
  };

  const setActive = (id: string) => {
    const newModels = models.map((entry) => ({
      ...entry,
      active: entry.id === id,
    }));
    onModelsChange(newModels);
    onAutoSave?.(newModels);
  };

  const removeModel = (id: string) => {
    const remaining = models.filter((entry) => entry.id !== id);
    if (remaining.length === 0) return;
    if (models.find((entry) => entry.id === id)?.active) {
      remaining[0] = { ...remaining[0], active: true };
    }
    onModelsChange(remaining);
    setExpandedId((prev) =>
      prev === id ? (remaining.length === 1 ? remaining[0].id : null) : prev,
    );
  };

  const toggleExpanded = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  return (
    <div className="settings-form">
      <div className="settings-models-hint-row">
        <p className="settings-field-hint-inline settings-models-hint">
          {t(
            "settings.modelsHint",
            "可配置多个提供方，对话时在输入框发送按钮左侧快速切换模型；提供商目录可在配置文件里自定义，直接让 Agent 帮你增改即可",
          )}
        </p>
        <Button
          variant="icon"
          onClick={() => {
            void openProviderConfigDir();
          }}
          aria-label={t("settings.openConfigDir", "打开提供商配置文件目录")}
          title={t("settings.openConfigDir", "打开提供商配置文件目录")}
        >
          <Sparkles size={14} />
        </Button>
      </div>
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
                <div
                  role="button"
                  tabIndex={0}
                  className="settings-model-summary"
                  onClick={() => toggleExpanded(entry.id)}
                  aria-expanded={expanded}
                  title={
                    expanded
                      ? t("settings.collapseModel", "收起")
                      : t("settings.expandModel", "展开编辑")
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      toggleExpanded(entry.id);
                    }
                  }}
                >
                  <span className="settings-model-name">
                    {entry.name ||
                      entry.model ||
                      (entry.custom_models || "")
                        .split(/[,，]/)
                        .map((s) => s.trim())
                        .find(Boolean) ||
                      t("settings.modelUnnamed", "未命名模型")}
                  </span>
                  {entry.active && (
                    <Tag tone="accent" icon={<Star size={10} fill="currentColor" />}>
                      {t("settings.defaultBadge", "默认")}
                    </Tag>
                  )}
                  {balances[entry.id]?.available && (
                    <Tag tone="success">¥{balances[entry.id].balance}</Tag>
                  )}
                </div>
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
                            color={entry.active ? "var(--color-accent)" : undefined}
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
                        label: t("settings.deleteModel", "删除"),
                        description: /deepseek/i.test(entry.base_url)
                          ? t("settings.baseModelNoDelete", "基础提供方不可删除")
                          : undefined,
                        // DeepSeek 作为基础提供方不可删除，仅剩一个提供方时也不可删除
                        disabled: models.length <= 1 || /deepseek/i.test(entry.base_url),
                        onClick: () => {
                          // 弹窗展示提供方 label（如 DeepSeek、Xiaomi (MiMo)），而不是模型名
                          const providerKey = getEntryProvider(entry);
                          const providerLabel =
                            PROVIDER_OPTIONS.find((o) => o.value === providerKey)?.label ??
                            providerKey ??
                            t("settings.modelUnnamed", "未命名提供方");
                          const doRemove = () => removeModel(entry.id);
                          if (onConfirm) {
                            onConfirm(
                              t("settings.deleteModelConfirmTitle", "删除"),
                              t(
                                "settings.deleteModelConfirmMessage",
                                "确定删除「{{name}}」吗？点击「保存」后生效。",
                                { name: providerLabel },
                              ),
                              doRemove,
                            );
                          } else {
                            doRemove();
                          }
                        },
                      },
                    ]}
                  />
                )}
                <div
                  role="button"
                  tabIndex={0}
                  className={`settings-model-chevron${expanded ? " open" : ""}`}
                  onClick={() => toggleExpanded(entry.id)}
                  aria-label={
                    expanded
                      ? t("settings.collapseModel", "收起")
                      : t("settings.expandModel", "展开编辑")
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      toggleExpanded(entry.id);
                    }
                  }}
                >
                  <ChevronDown size={14} />
                </div>
              </div>
              {expanded && (
                <div className="settings-model-card-body">
                  <Select
                    label={t("settings.provider", "提供方")}
                    value={getEntryProvider(entry)}
                    onChange={(value) => handleProviderChange(entry.id, value)}
                    options={vendorOptionsFor(entry)}
                    placeholder="选择提供方"
                  />
                  <Input
                    label={t("settings.apiKeyLabel", "API Key{{saved}}", {
                      saved: entry.has_api_key ? t("settings.saved", "（已保存）") : "",
                    })}
                    type={showKeys[entry.id] ? "text" : "password"}
                    value={modelKeys[entry.id] ?? ""}
                    onChange={(event) => onModelKeyChange(entry.id, event.target.value)}
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
                        {showKeys[entry.id] ? <EyeOff size={14} /> : <Eye size={14} />}
                      </Button>
                    }
                  />
                  <div className={`settings-custom-toggle${customOpen[entry.id] ? " open" : ""}`}>
                    <div
                      className="settings-custom-toggle-header"
                      role="button"
                      tabIndex={0}
                      onClick={() => toggleCustomSettings(entry.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggleCustomSettings(entry.id);
                        }
                      }}
                      aria-expanded={Boolean(customOpen[entry.id])}
                    >
                      <span>{t("settings.customSettings", "自定义设置")}</span>
                      <ChevronDown size={14} className="settings-custom-toggle-chevron" />
                    </div>
                    {customOpen[entry.id] && (
                      <div className="settings-custom-fields">
                        <Input
                          label="Base URL"
                          value={entry.base_url}
                          onChange={(event) =>
                            updateModel(entry.id, { base_url: event.target.value })
                          }
                          placeholder={
                            getEntryProvider(entry) === "custom"
                              ? "输入 API 地址"
                              : "选择提供方后自动回填"
                          }
                        />
                        <Select
                          label={t("settings.toolMode", "工具调用方式")}
                          value={entry.tool_mode ?? "auto"}
                          onChange={(value) =>
                            updateModel(entry.id, { tool_mode: value as ToolMode })
                          }
                          options={toolModeOptions(t)}
                        />
                        <p className="settings-field-hint settings-model-tool-mode-hint">
                          {t(
                            "settings.toolModeHint",
                            "ReAct 文本模式适用于不支持原生函数调用的模型或接口（如部分本地推理服务），以 Thought/Action 文本循环调用工具",
                          )}
                        </p>
                        <Input
                          label={t("settings.customModels", "自定义模型")}
                          value={entry.custom_models ?? ""}
                          onChange={(event) =>
                            updateModel(entry.id, {
                              custom_models: event.target.value,
                            })
                          }
                          placeholder="输入自定义模型名，多个用逗号分隔"
                        />
                      </div>
                    )}
                  </div>
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
