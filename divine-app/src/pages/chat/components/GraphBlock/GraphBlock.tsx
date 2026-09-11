/**
 * GraphBlock —— 聊天内嵌图形容器。
 *
 * 结构对齐 MermaidBlock / ECharts 块（头部 34px、画布可滚动、工具条常驻），
 * 差别是工具条**常驻可见**：播放与流动开关是"持续状态"，hover 才出现的话
 * 用户判断不了当前开着没有（020 §11.3）。
 *
 * 历史消息走 `animate=false`（直渲染终态、零动画、不自动开流动）。
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  Download,
  FileCode2,
  LoaderCircle,
  Pause,
  Play,
  RotateCcw,
  Waves,
} from "lucide-react";
import { toast } from "@/components/ui/Toast";
import { useTheme } from "@/services/theme";
import { isTauri, openFileLocation, saveExportFile } from "@/services/tauri";
import { type GraphIR, KIND_LABELS, type GraphNode, nodeTone } from "./GraphIR";
import { createGraphRenderer, type GraphRendererApi } from "./GraphRenderer";
import { branchColor, TONE_LABELS } from "./graphTones";
import { resolvePreset } from "./presets";
import "./index.less";

interface GraphBlockProps {
  ir: GraphIR;
  workspacePath?: string | null;
  /** 新消息 = true（回放式入场）；历史消息 = false（直渲染终态） */
  animate?: boolean;
}

/** base64 载荷（Promise 包装 FileReader，与图表导出同路径）。 */
function toBase64Payload(dataUrl: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const comma = dataUrl.indexOf(",");
    if (comma < 0) {
      reject(new Error("invalid data url"));
      return;
    }
    const head = dataUrl.slice(0, comma);
    const body = dataUrl.slice(comma + 1);
    if (head.includes("base64")) {
      resolve(body);
      return;
    }
    // percent-encoded（X6 的 toSVG 走这条）→ 统一经 Blob 重编码
    const blob = new Blob([decodeURIComponent(body)], { type: "image/svg+xml" });
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.readAsDataURL(blob);
  });
}

function triggerDownload(objectUrl: string, filename: string) {
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function GraphBlock({ ir, workspacePath, animate = false }: GraphBlockProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  // 渲染器实例存 state 而非 ref：工具条回调要传给工具按钮组件，
  // 回调里读 ref.current 会触发 React Compiler 的「渲染期不得访问 ref」规则。
  const [renderer, setRenderer] = useState<GraphRendererApi | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [flowOn, setFlowOn] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [saving, setSaving] = useState<"png" | "svg" | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);

  const preset = useMemo(() => resolvePreset(ir.kind), [ir.kind]);
  const title = ir.meta?.title || KIND_LABELS[ir.kind];

  // 类别色点（图例用）：按首次出现顺序，与渲染器同一套分配规则
  const categories = useMemo(() => {
    const seen: { name: string; count: number; index: number }[] = [];
    for (const node of ir.nodes) {
      if (!node.category) continue;
      const existing = seen.find((item) => item.name === node.category);
      if (existing) existing.count += 1;
      else if (seen.length < 5) {
        seen.push({ name: node.category, count: 1, index: seen.length });
      }
    }
    return seen;
  }, [ir.nodes]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let disposed = false;
    let api: GraphRendererApi | null = null;
    setError(null);
    setSelected(null);
    setFlowOn(false);

    void createGraphRenderer({
      container,
      ir,
      preset,
      theme: theme === "light" ? "light" : "dark",
      animate,
      onSelectNode: (node) => setSelected(node),
    })
      .then((created) => {
        if (disposed) {
          created.dispose();
          return;
        }
        api = created;
        setRenderer(created);
      })
      .catch((err) => {
        console.error("[GraphBlock] 渲染失败:", err);
        if (!disposed) setError(err instanceof Error ? err.message : String(err));
      });

    return () => {
      disposed = true;
      api?.dispose();
      setRenderer((prev) => (prev === api ? null : prev));
    };
  }, [ir, preset, theme, animate]);

  const toggleFlow = () => {
    if (!renderer) return;
    const next = !flowOn;
    renderer.setFlow(next);
    setFlowOn(next);
  };

  const replay = () => {
    renderer?.replay();
  };

  const toggleDemo = () => {
    if (!renderer) return;
    if (playing) {
      renderer.stopDemo();
      setPlaying(false);
    } else {
      renderer.playDemo();
      setPlaying(true);
    }
  };

  const exportGraph = async (format: "png" | "svg") => {
    if (!renderer || saving) return;
    setSaving(format);
    try {
      // 兜底名必须可纯计算：Date.now() 是不纯函数，React Compiler 会拒绝
      const stem =
        title.replace(/[\\/:*?"<>|\s]+/g, "_").slice(0, 48) || `${ir.kind}-${ir.nodes.length}`;
      const target = `graph-${stem}.${format}`;
      if (format === "svg") {
        const svg = await renderer.exportSVG();
        const payload = await toBase64Payload(
          `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
        );
        if (isTauri() && workspacePath) {
          const saved = await saveExportFile(workspacePath, payload, target);
          toast.success(t("chat.exportSaved", "已导出：{{name}}", { name: saved.name }), {
            label: t("chat.openFolder", "打开"),
            onClick: () => void openFileLocation(saved.path),
          });
        } else {
          const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
          try {
            triggerDownload(url, target);
          } finally {
            URL.revokeObjectURL(url);
          }
        }
      } else {
        const dataUrl = await renderer.exportPNG(2);
        const payload = await toBase64Payload(dataUrl);
        if (isTauri() && workspacePath) {
          const saved = await saveExportFile(workspacePath, payload, target);
          toast.success(t("chat.exportSaved", "已导出：{{name}}", { name: saved.name }), {
            label: t("chat.openFolder", "打开"),
            onClick: () => void openFileLocation(saved.path),
          });
        } else {
          const response = await fetch(dataUrl);
          const url = URL.createObjectURL(await response.blob());
          try {
            triggerDownload(url, target);
          } finally {
            URL.revokeObjectURL(url);
          }
        }
      }
    } catch (err) {
      console.error("[GraphBlock] 导出失败:", err);
      toast.error(t("chat.exportFailed", "导出失败，请重试"));
    } finally {
      setSaving(null);
    }
  };

  const toolbarButton = (
    key: string,
    label: string,
    icon: ReactNode,
    onClick: () => void,
    active = false,
  ) => (
    <div
      key={key}
      role="button"
      tabIndex={0}
      className={`gb-btn${active ? " on" : ""}`}
      title={label}
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      onKeyDown={(event: ReactKeyboardEvent<HTMLDivElement>) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick();
        }
      }}
    >
      {icon}
    </div>
  );

  return (
    <div className="gb-block" role="group" aria-label={`${KIND_LABELS[ir.kind]}：${title}`}>
      <div className="gb-header">
        <span>{title}</span>
        <div className="gb-tools">
          {preset.capabilities.includes("play") &&
            (playing
              ? toolbarButton(
                  "demo",
                  t("chat.graphStopDemo", "停止演示"),
                  <Pause size={13} />,
                  toggleDemo,
                  true,
                )
              : ir.demoPath?.length
                ? toolbarButton(
                    "demo",
                    t("chat.graphPlayDemo", "播放演示"),
                    <Play size={13} />,
                    toggleDemo,
                  )
                : null)}
          {animate &&
            toolbarButton(
              "replay",
              t("chat.graphReplay", "重播入场"),
              <RotateCcw size={13} />,
              replay,
            )}
          {preset.capabilities.includes("flow") &&
            toolbarButton(
              "flow",
              flowOn ? t("chat.graphFlowOff", "关闭流动") : t("chat.graphFlowOn", "开启流动"),
              <Waves size={13} />,
              toggleFlow,
              flowOn,
            )}
          {preset.capabilities.includes("export") && (
            <>
              {toolbarButton(
                "png",
                t("chat.exportPng", "导出 PNG 图片"),
                saving === "png" ? (
                  <LoaderCircle size={13} className="spin" />
                ) : (
                  <Download size={13} />
                ),
                () => void exportGraph("png"),
              )}
              {toolbarButton(
                "svg",
                t("chat.exportSvg", "导出 SVG 矢量图"),
                saving === "svg" ? (
                  <LoaderCircle size={13} className="spin" />
                ) : (
                  <FileCode2 size={13} />
                ),
                () => void exportGraph("svg"),
              )}
            </>
          )}
        </div>
      </div>

      <div className="gb-canvas-wrap">
        <div ref={containerRef} className="gb-canvas" />
        {error && (
          <div className="gb-error">
            <AlertTriangle size={14} />
            <span>{t("chat.graphRenderFailed", "图形数据异常，暂时无法渲染，可重新生成试试")}</span>
          </div>
        )}
      </div>

      {preset.legend && (categories.length > 0 || ir.edges.length > 0) && !error && (
        <div className="gb-legend">
          {categories.map((category) => (
            <span key={category.name} className="gb-chip">
              <i
                style={{
                  background: branchColor(category.index, theme === "light" ? "light" : "dark"),
                }}
              />
              {category.name}
              <em>×{category.count}</em>
            </span>
          ))}
          <span className="gb-chip gb-chip-line">
            <svg width="24" height="8" aria-hidden>
              <line x1="0" y1="4" x2="24" y2="4" className="solid" />
            </svg>
            {t("chat.graphSyncCall", "同步调用")}
          </span>
          <span className="gb-chip gb-chip-line">
            <svg width="24" height="8" aria-hidden>
              <line x1="0" y1="4" x2="24" y2="4" className="dashed" />
            </svg>
            {t("chat.graphAsyncMsg", "异步消息")}
          </span>
        </div>
      )}

      {selected && (
        <div className="gb-inspector">
          <span
            className="gb-inspector-bar"
            style={{ background: nodeTone(selected) === "neutral" ? "transparent" : undefined }}
          />
          <div className="gb-inspector-body">
            <div className="gb-inspector-title">{selected.label ?? selected.id}</div>
            {selected.note ? (
              <p>{selected.note}</p>
            ) : (
              <p>
                {KIND_LABELS[ir.kind]}
                {TONE_LABELS[nodeTone(selected)] ? ` · ${TONE_LABELS[nodeTone(selected)]}` : ""}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
