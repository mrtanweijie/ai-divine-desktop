// 「生成模型」设置分区（036 §9 / 035 §10）：图像与视频两组，与聊天模型完全分离。
// 供应商下拉选中后自动回填 base_url 与模型候选；key 空值 = 保留已存（后端合并语义）。
import { ChevronDown, Film, Plus, Star, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Tag } from "@/components/ui/Tag";
import type { MediaModelConfig, MediaModelPayload } from "@/types";
import "./MediaSection.less";

export interface MediaModelDraft {
  id: string;
  kind: "image" | "video";
  label: string;
  provider: string;
  base_url: string;
  model: string;
  options: Record<string, unknown>;
  has_api_key: boolean;
  api_key: string;
  active: boolean;
}

interface MediaSectionProps {
  models: MediaModelConfig[];
  onChange: (models: MediaModelDraft[]) => void;
  /** 保存由外层设置面板统一处理（媒体分区即时保存，见 pages/settings/index.tsx） */
}

const PROVIDER_PRESETS: Record<string, { base_url: string; models: string[]; label: string }> = {
  minimax: {
    base_url: "https://api.minimaxi.com",
    models: ["MiniMax-H3", "MiniMax-H3-Max"],
    label: "MiniMax",
  },
  zhipu: {
    base_url: "https://open.bigmodel.cn",
    models: ["cogvideox-flash"],
    label: "智谱",
  },
  glm: {
    base_url: "https://open.bigmodel.cn",
    models: ["glm-image"],
    label: "智谱（图像）",
  },
};

const PROVIDERS_BY_KIND: Record<"image" | "video", string[]> = {
  image: ["minimax", "glm"],
  video: ["minimax", "zhipu"],
};

const KIND_LABELS: Record<"image" | "video", string> = {
  video: "视频",
  image: "图像",
};

/** 事件处理器里生成新条目 id（放模块作用域，避免在渲染作用域调 Date.now/random） */
function newMediaId(): string {
  return `media-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

export function MediaSection({ models, onChange }: MediaSectionProps) {
  const { t } = useTranslation();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const drafts: MediaModelDraft[] = models.map(toMediaDraft);

  const update = (id: string, patch: Partial<MediaModelDraft>) => {
    onChange(drafts.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry)));
  };

  const add = (kind: "image" | "video") => {
    const provider = PROVIDERS_BY_KIND[kind][0];
    const preset = PROVIDER_PRESETS[provider];
    const entry: MediaModelDraft = {
      id: newMediaId(),
      kind,
      label: "",
      provider,
      base_url: preset.base_url,
      model: preset.models[0] ?? "",
      options: {},
      has_api_key: false,
      api_key: "",
      active: false,
    };
    onChange([...drafts, entry]);
    setExpandedId(entry.id);
  };

  const remove = (id: string) => {
    onChange(drafts.filter((entry) => entry.id !== id));
  };

  /** 每 kind 至多一个 active（后端 normalize 也会兜一次） */
  const setActive = (id: string) => {
    const target = drafts.find((entry) => entry.id === id);
    if (!target) return;
    onChange(
      drafts.map((entry) =>
        entry.kind === target.kind ? { ...entry, active: entry.id === id } : entry,
      ),
    );
  };

  const groups: Array<"video" | "image"> = ["video", "image"];

  return (
    <div className="settings-form media-section">
      <p className="settings-field-hint-inline">
        {t(
          "settings.mediaHint",
          "生成图像/视频用的模型，与对话模型分离；key 只保存在本机。单价用于预估费用，请按服务商最新价格表填写",
        )}
      </p>
      {groups.map((kind) => {
        const entries = drafts.filter((entry) => entry.kind === kind);
        return (
          <div key={kind} className="media-group">
            <div className="media-group-header">
              <h3 className="media-group-title">
                {t(`settings.mediaKind.${kind}`, KIND_LABELS[kind])}
              </h3>
              <Button
                variant="ghost"
                size="small"
                onClick={() => add(kind)}
                aria-label={t("settings.mediaAdd", "添加")}
              >
                <Plus size={13} />
                {t("settings.mediaAdd", "添加")}
              </Button>
            </div>
            {entries.length === 0 && (
              <p className="media-group-empty">
                {t("settings.mediaEmpty", "未配置；图像/视频生成功能需要至少一个模型")}
              </p>
            )}
            {entries.map((entry) => {
              const expanded = expandedId === entry.id;
              const preset = PROVIDER_PRESETS[entry.provider];
              const providerOptions = PROVIDERS_BY_KIND[kind].map((value) => ({
                value,
                label: PROVIDER_PRESETS[value]?.label ?? value,
              }));
              return (
                <div
                  key={entry.id}
                  className={`media-model-card${entry.active ? " is-active" : ""}${
                    expanded ? " is-expanded" : ""
                  }`}
                >
                  <div
                    role="button"
                    tabIndex={0}
                    className="media-model-summary"
                    onClick={() => setExpandedId(expanded ? null : entry.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setExpandedId(expanded ? null : entry.id);
                      }
                    }}
                  >
                    <span className="media-model-name">
                      {entry.label || entry.model || t("settings.mediaUnnamed", "未命名模型")}
                    </span>
                    {entry.active && (
                      <Tag tone="accent" icon={<Star size={10} fill="currentColor" />}>
                        {t("settings.mediaDefault", "默认")}
                      </Tag>
                    )}
                    {entry.has_api_key && (
                      <Tag tone="success">{t("settings.mediaKeySet", "已配 Key")}</Tag>
                    )}
                    <ChevronDown
                      size={13}
                      className={`media-model-chevron${expanded ? " open" : ""}`}
                    />
                  </div>
                  {expanded && (
                    <div className="media-model-fields">
                      <div className="media-field-row">
                        <Select
                          label={t("settings.mediaProvider", "供应商")}
                          value={entry.provider}
                          options={providerOptions}
                          onChange={(value) => {
                            const nextPreset = PROVIDER_PRESETS[value];
                            update(entry.id, {
                              provider: value,
                              base_url: nextPreset?.base_url ?? entry.base_url,
                              model: nextPreset?.models[0] ?? entry.model,
                            });
                          }}
                        />
                        <Input
                          label={t("settings.mediaModelName", "模型")}
                          value={entry.model}
                          placeholder={preset?.models[0] ?? ""}
                          onChange={(event) => update(entry.id, { model: event.target.value })}
                        />
                      </div>
                      <Input
                        label={t("settings.mediaBaseUrl", "API 地址（主机，选填）")}
                        value={entry.base_url}
                        placeholder={preset?.base_url ?? ""}
                        onChange={(event) => update(entry.id, { base_url: event.target.value })}
                      />
                      <Input
                        label={t("settings.mediaApiKey", "API Key")}
                        type="password"
                        value={entry.api_key}
                        placeholder={
                          entry.has_api_key
                            ? t("settings.mediaKeySaved", "已保存（输入新值覆盖）")
                            : t("settings.mediaKeyMissing", "必填")
                        }
                        onChange={(event) => update(entry.id, { api_key: event.target.value })}
                      />
                      {kind === "video" ? (
                        <div className="media-field-row">
                          <Input
                            label={t("settings.mediaDuration", "默认时长（秒）")}
                            value={String(entry.options.duration ?? "")}
                            onChange={(event) =>
                              update(entry.id, {
                                options: {
                                  ...entry.options,
                                  duration: Number(event.target.value) || undefined,
                                },
                              })
                            }
                          />
                          <Input
                            label={t("settings.mediaPrice", "每秒单价（元，选填）")}
                            value={String(entry.options.price_per_second ?? "")}
                            placeholder="如 0.07"
                            onChange={(event) =>
                              update(entry.id, {
                                options: {
                                  ...entry.options,
                                  price_per_second: Number(event.target.value) || undefined,
                                },
                              })
                            }
                          />
                        </div>
                      ) : null}
                      <div className="media-model-footer">
                        {!entry.active && (
                          <Button variant="ghost" size="small" onClick={() => setActive(entry.id)}>
                            <Star size={12} />
                            {t("settings.mediaSetDefault", "设为默认")}
                          </Button>
                        )}
                        <Button variant="ghost" size="small" onClick={() => remove(entry.id)}>
                          <Trash2 size={12} />
                          {t("common.delete", "删除")}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
      <p className="settings-field-hint-inline media-note">
        <Film size={12} />
        {t(
          "settings.mediaNote",
          "这里配置的默认时长/分辨率/比例会预填到生成面板；测试连通性暂未提供，保存后直接生成即可验证",
        )}
      </p>
    </div>
  );
}

/** 服务端条目 → 可编辑草稿（api_key 置空，提交空串 = 保留已存值） */
export function toMediaDraft(entry: MediaModelConfig): MediaModelDraft {
  return { ...entry, api_key: "" };
}

/** 草稿 → 保存载荷（api_key 空串 = 保留已存值） */
export function toMediaPayload(models: MediaModelDraft[]): MediaModelPayload[] {
  return models.map((entry) => ({
    id: entry.id,
    kind: entry.kind,
    label: entry.label,
    provider: entry.provider,
    base_url: entry.base_url,
    model: entry.model,
    options: entry.options,
    api_key: entry.api_key,
    active: entry.active,
  }));
}
