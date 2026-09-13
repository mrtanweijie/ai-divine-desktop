import { ChevronLeft, ChevronRight, Sparkles } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";
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

type MenuLevel = "main" | "models";

const EFFORT_ITEMS = ["off", "low", "high", "max"] as const;
const KNOB_SIZE = 28;

// 档位在轨道上的水平位置：两端内缩，刻度/knob 不超出胶囊
const sliderPos = (ratio: number): string =>
  `calc(${KNOB_SIZE / 2}px + ${(ratio * 100).toFixed(2)}% - ${(ratio * KNOB_SIZE).toFixed(2)}px)`;

// 填充宽度：从槽最左铺到 knob 中心（覆盖槽左圆头），knob 半径处由 knob 自身覆盖
const sliderFillWidth = (ratio: number): string =>
  `calc(${KNOB_SIZE / 2}px + ${(ratio * 100).toFixed(2)}% - ${(ratio * KNOB_SIZE).toFixed(2)}px)`;

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
  const [dragging, setDragging] = useState(false);
  const draggingRef = useRef(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  const currentModel =
    models.find((m) => m.id === modelId) ?? models.find((m) => m.active) ?? models[0] ?? null;
  const currentModelName =
    currentModel?.name || currentModel?.model || t("chat.switchModel", "切换模型");

  // 吸附式离散滑块：值域只有 4 个档位，任何落点都吸附到最近刻度
  const effortIndex = Math.max(0, EFFORT_ITEMS.indexOf(effort as (typeof EFFORT_ITEMS)[number]));

  const setEffortFromClientX = (clientX: number) => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return;
    // 行程两端内缩 knob 半径，保证刻度与 knob 恒在胶囊轨道内
    const inset = KNOB_SIZE / 2;
    const ratio = Math.min(
      1,
      Math.max(0, (clientX - rect.left - inset) / (rect.width - inset * 2)),
    );
    const nearest = Math.round(ratio * (EFFORT_ITEMS.length - 1));
    const key = EFFORT_ITEMS[nearest];
    if (key !== effort) onEffortChange(key);
  };

  const onTrackPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    // 拖拽期间挂 window 级监听：不依赖指针捕获与组件重渲染时序，
    // 移出轨道/面板范围也能持续吸附更新
    draggingRef.current = true;
    setDragging(true);
    setEffortFromClientX(e.clientX);
  };
  const endDrag = () => {
    draggingRef.current = false;
    setDragging(false);
  };

  // 拖拽中：window 级 pointermove/pointerup，替代元素级捕获
  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: PointerEvent) => setEffortFromClientX(e.clientX);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", endDrag);
    window.addEventListener("pointercancel", endDrag);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", endDrag);
      window.removeEventListener("pointercancel", endDrag);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dragging, effort]);

  const onSliderKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;
    const idx = effortIndex;
    let next: (typeof EFFORT_ITEMS)[number] | null = null;
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
      next = EFFORT_ITEMS[Math.max(0, idx - 1)];
    } else if (e.key === "ArrowRight" || e.key === "ArrowUp") {
      next = EFFORT_ITEMS[Math.min(EFFORT_ITEMS.length - 1, idx + 1)];
    } else if (e.key === "Home") {
      next = EFFORT_ITEMS[0];
    } else if (e.key === "End") {
      next = EFFORT_ITEMS[EFFORT_ITEMS.length - 1];
    }
    if (next && next !== effort) {
      e.preventDefault();
      onEffortChange(next);
    }
  };

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
              <div className="model-effort-main">
                <div
                  className="model-effort-context"
                  role="button"
                  tabIndex={disabled ? -1 : 0}
                  onClick={() => setLevel("models")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setLevel("models");
                    }
                  }}
                  title={t("chat.switchModel", "切换模型")}
                >
                  <span className="model-effort-context-effort">
                    {effortLabels[effort] ?? "关闭"}
                    <ChevronRight size={13} />
                  </span>
                  <span className="model-effort-context-model">{currentModelName}</span>
                </div>

                <div className="model-effort-slider-block">
                  <div
                    ref={trackRef}
                    className={`model-effort-slider${dragging ? " dragging" : ""}`}
                    role="slider"
                    tabIndex={disabled ? -1 : 0}
                    aria-label={t("chat.thinkEffort", "深度思考")}
                    aria-valuemin={0}
                    aria-valuemax={EFFORT_ITEMS.length - 1}
                    aria-valuenow={effortIndex}
                    aria-valuetext={effortLabels[effort] ?? "关闭"}
                    onPointerDown={onTrackPointerDown}
                    onKeyDown={onSliderKeyDown}
                  >
                    {/* 关闭档（index 0）无填充：14px 圆角小条会从圆形 knob 边缘露出 */}
                    {effortIndex > 0 && (
                      <div
                        className="model-effort-slider-fill"
                        style={{
                          width: sliderFillWidth(effortIndex / (EFFORT_ITEMS.length - 1)),
                        }}
                      />
                    )}
                    {EFFORT_ITEMS.map((key, i) => (
                      <span
                        key={key}
                        className={`model-effort-slider-tick${i <= effortIndex ? " filled" : ""}${
                          i === effortIndex ? " active" : ""
                        }`}
                        style={{
                          left: sliderPos(i / (EFFORT_ITEMS.length - 1)),
                        }}
                      />
                    ))}
                    <span
                      className="model-effort-slider-knob"
                      style={{
                        left: sliderPos(effortIndex / (EFFORT_ITEMS.length - 1)),
                      }}
                    />
                  </div>
                  <div className="model-effort-slider-scale">
                    {EFFORT_ITEMS.map((key) => (
                      <span key={key} className={key === effort ? "active" : ""}>
                        {effortLabels[key]}
                      </span>
                    ))}
                  </div>
                  <div className="model-effort-slider-desc">
                    {effortDescriptions[effort] ?? effortDescriptions.high}
                  </div>
                </div>
              </div>
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
                  <span>{t("settings.model", "模型")}</span>
                </div>
                <ul className="model-effort-menu" role="menu">
                  {(() => {
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
                  })()}
                </ul>
              </>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
