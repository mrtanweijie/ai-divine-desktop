import { ChevronLeft, ChevronRight, Sparkles } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import type { ModelConfig } from "@/types";
import { PROVIDER_LIST, groupModelsByProvider } from "@/config/providers";
import "./ModelEffortControl.less";

interface ModelEffortControlProps {
  disabled?: boolean;
  models: ModelConfig[];
  modelId: string | null;
  onModelChange: (modelId: string) => void;
  effort: string;
  onEffortChange: (value: string) => void;
}

type MenuLevel = "main" | "models" | "efforts";

const EFFORT_ITEMS = ["off", "low", "high", "max"] as const;

// 获取提供商标签
function getProviderLabel(providerKey: string): string {
  const config = PROVIDER_LIST.find((p) => p.value === providerKey);
  return config?.label || providerKey;
}

export function ModelEffortControl({
  disabled,
  models,
  modelId,
  onModelChange,
  effort,
  onEffortChange,
}: ModelEffortControlProps) {
  const { t } = useTranslation();

  const effortLabels: Record<string, string> = {
    off: t("chat.effortOff", "关闭"),
    low: t("settings.effortLow", "低"),
    high: t("settings.effortHigh", "高"),
    max: t("settings.effortMax", "最高"),
  };
  const effortDescriptions: Record<string, string> = {
    off: t("chat.effortOffDescription", "不进行深度思考，响应最快"),
    low: t("chat.effortLowDescription", "更快的回答，思考较少"),
    high: t("chat.effortHighDescription", "默认档位"),
    max: t("chat.effortMaxDescription", "最深入的思考"),
  };

  const [open, setOpen] = useState(false);
  const [level, setLevel] = useState<MenuLevel>("main");
  const [panelStyle, setPanelStyle] = useState<CSSProperties>({});
  const wrapperRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const currentModel =
    models.find((m) => m.id === modelId) ?? models.find((m) => m.active) ?? models[0] ?? null;
  const currentModelName =
    currentModel?.name || currentModel?.model || t("chat.switchModel", "切换模型");

  useEffect(() => {
    if (!open || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setPanelStyle({
      position: "fixed",
      bottom: window.innerHeight - rect.top + 6,
      right: window.innerWidth - rect.right,
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (wrapperRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // 关闭时重置层级：渲染期调整（React 官方建议，替代 effect 内 setState）
  const [prevOpen, setPrevOpen] = useState(open);
  if (prevOpen !== open) {
    setPrevOpen(open);
    if (!open) setLevel("main");
  }

  const triggerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setOpen((v) => !v);
    }
  };

  const selectModel = (id: string) => {
    onModelChange(id);
    setOpen(false);
  };

  const selectEffort = (key: string) => {
    onEffortChange(key);
    setOpen(false);
  };

  return (
    <div className="model-effort-control" ref={wrapperRef}>
      <div
        ref={triggerRef}
        className="model-effort-trigger"
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => !disabled && setOpen((v) => !v)}
        onKeyDown={triggerKeyDown}
        title={t("chat.modelEffortTooltip", "模型与推理设置")}
      >
        <Sparkles size={12} />
        <span className="model-effort-trigger-label">{currentModelName}</span>
        <span className="model-effort-trigger-sep">·</span>
        <span className="model-effort-trigger-label">{effortLabels[effort] ?? "关闭"}</span>
        <ChevronRight size={10} />
      </div>

      {open &&
        createPortal(
          <div ref={panelRef} className="model-effort-panel" style={panelStyle}>
            {level === "main" ? (
              <ul className="model-effort-menu" role="menu">
                <li
                  role="menuitem"
                  tabIndex={0}
                  className="model-effort-menu-item"
                  onClick={() => setLevel("models")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") setLevel("models");
                  }}
                >
                  <span className="model-effort-menu-left">
                    <span className="model-effort-menu-label">{t("settings.model", "模型")}</span>
                  </span>
                  <span className="model-effort-menu-right">
                    <span className="model-effort-menu-value">{currentModelName}</span>
                    <ChevronRight size={12} />
                  </span>
                </li>
                <li
                  role="menuitem"
                  tabIndex={0}
                  className="model-effort-menu-item"
                  onClick={() => setLevel("efforts")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") setLevel("efforts");
                  }}
                >
                  <span className="model-effort-menu-left">
                    <span className="model-effort-menu-label">
                      {t("chat.thinkEffort", "深度思考")}
                    </span>
                  </span>
                  <span className="model-effort-menu-right">
                    <span className="model-effort-menu-value">
                      {effortLabels[effort] ?? "关闭"}
                    </span>
                    <ChevronRight size={12} />
                  </span>
                </li>
              </ul>
            ) : (
              <>
                <div
                  className="model-effort-back"
                  role="button"
                  tabIndex={0}
                  onClick={() => setLevel("main")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") setLevel("main");
                  }}
                >
                  <ChevronLeft size={14} />
                  <span>
                    {level === "models"
                      ? t("settings.model", "模型")
                      : t("chat.thinkEffort", "深度思考")}
                  </span>
                </div>
                <ul className="model-effort-menu" role="menu">
                  {level === "models"
                    ? (() => {
                        const grouped = groupModelsByProvider(models);
                        const items: React.ReactNode[] = [];

                        grouped.forEach((groupModels, providerKey) => {
                          const providerLabel =
                            providerKey === "custom"
                              ? t("settings.custom", "自定义")
                              : getProviderLabel(providerKey);

                          // 添加分组标题
                          items.push(
                            <li key={`header-${providerKey}`} className="model-effort-menu-header">
                              <span>{providerLabel}</span>
                            </li>,
                          );

                          // 添加该分组下的模型
                          groupModels.forEach((entry) => {
                            items.push(
                              <li
                                key={entry.id}
                                role="menuitem"
                                tabIndex={0}
                                className={`model-effort-menu-item${
                                  entry.id === modelId ? " selected" : ""
                                }`}
                                onClick={() => selectModel(entry.id)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") selectModel(entry.id);
                                }}
                              >
                                <span>{entry.name || entry.model}</span>
                              </li>,
                            );
                          });
                        });

                        return items;
                      })()
                    : EFFORT_ITEMS.map((key) => (
                        <li
                          key={key}
                          role="menuitem"
                          tabIndex={0}
                          className={`model-effort-menu-item${key === effort ? " selected" : ""}`}
                          onClick={() => selectEffort(key)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") selectEffort(key);
                          }}
                        >
                          <span>{effortLabels[key]}</span>
                          <small>{effortDescriptions[key]}</small>
                        </li>
                      ))}
                </ul>
              </>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
