import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Download, FileCode2, LoaderCircle } from "lucide-react";
import type { ECharts } from "echarts";
import { useTheme } from "@/services/theme";
import { isTauri, openFileLocation, saveExportFile } from "@/services/tauri";
import { toast } from "@/components/ui/Toast";
import { buildChartOption, chartHeight } from "./chartOptions";

interface ChartBlockProps {
  option: Record<string, unknown>;
  /** 当前会话工作区路径：桌面端导出图表时经 Tauri 落盘到 <workspace>/charts/ */
  workspacePath?: string | null;
}

type ExportFormat = "png" | "svg";

/** 从 option.title（字符串或 {text}）提炼下载文件名，非法字符替换为 _ */
function chartFileName(option: Record<string, unknown>): string {
  let text = "";
  const title = option.title;
  if (typeof title === "string") {
    text = title;
  } else if (
    typeof title === "object" &&
    title !== null &&
    typeof (title as { text?: unknown }).text === "string"
  ) {
    text = (title as { text: string }).text;
  }
  const cleaned = text
    .replace(/[\\/:*?"<>|\s]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 60);
  return cleaned || `chart-${Date.now()}`;
}

/** 数据 URL → Blob 对象 URL（SVG 编码后很长，避免超长 href 触顶） */
async function toObjectUrl(dataUrl: string): Promise<string> {
  const response = await fetch(dataUrl);
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

/**
 * 数据 URL → base64 载荷（去掉 data: 前缀）。
 * ECharts 的 PNG 输出是 base64，但 SVG 输出是 percent-encoded 文本
 * （data:image/svg+xml;charset=UTF-8,...），不能直接 slice 当 base64 用，
 * 统一经 blob 重编码，保证 Rust 侧 STANDARD.decode 拿到 UTF-8 字节。
 */
async function toBase64Payload(dataUrl: string): Promise<string> {
  const blob = await (await fetch(dataUrl)).blob();
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error ?? new Error("read data url failed"));
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

export function ChartBlock({ option, workspacePath }: ChartBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ECharts | null>(null);
  const theme = useTheme();
  const { t } = useTranslation();
  // 渲染失败（数据损坏/option 非法）→ 覆盖层提示，而非白屏
  const [error, setError] = useState(false);
  // 导出进行中的格式（禁用重复点击）
  const [savingFormat, setSavingFormat] = useState<ExportFormat | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let disposed = false;
    let frame: number | undefined;
    let observer: ResizeObserver | undefined;
    let chart: ECharts | undefined;
    // option/主题变化 → 清掉上一次的失败提示，重新尝试渲染
    setError(false);

    void import("echarts")
      .then((echarts) => {
        if (disposed) return;
        try {
          chart = echarts.init(container);
          chartRef.current = chart;
        } catch (err) {
          console.error("ECharts init failed:", err);
          if (!disposed) setError(true);
          return;
        }
        frame = requestAnimationFrame(() => {
          try {
            chart?.setOption(buildChartOption(option, theme), {
              notMerge: true,
            });
          } catch (err) {
            // 非法 option（轴缺失/数据损坏等）→ 提示而非白屏
            console.error("Chart render failed:", err);
            if (!disposed) setError(true);
          }
        });
        observer = new ResizeObserver(() => chart?.resize());
        observer.observe(container);
      })
      .catch((err) => {
        console.error("Failed to load echarts:", err);
        if (!disposed) setError(true);
      });

    return () => {
      disposed = true;
      if (frame !== undefined) cancelAnimationFrame(frame);
      observer?.disconnect();
      chart?.dispose();
      chartRef.current = null;
    };
  }, [option, theme]);

  /**
   * 所见即所得导出：不开主实例，而是用同一份装饰后 option 在离屏
   * 容器重建一个无动画实例，按目标格式取图——canvas 渲染器出 PNG、
   * svg 渲染器出 SVG，与聊天里渲染的图表语义一致（ECharts 原生输出）。
   * 桌面端（Tauri）经 IPC 写入 <workspace>/charts/；浏览器环境回退为
   * 直接下载（WKWebView 会拦截跨手势的 a[download]，须走 Rust 落盘）。
   */
  const exportChart = async (format: ExportFormat) => {
    const container = containerRef.current;
    if (!container || !chartRef.current || savingFormat) return;
    const { clientWidth: width, clientHeight: height } = container;
    if (!width || !height) return;
    const fileName = chartFileName(option);
    setSavingFormat(format);
    try {
      const echarts = await import("echarts");
      const offscreen = document.createElement("div");
      Object.assign(offscreen.style, {
        position: "fixed",
        left: "-100000px",
        top: "0",
        width: `${width}px`,
        height: `${height}px`,
      });
      document.body.appendChild(offscreen);
      let instance: ECharts | undefined;
      let dataUrl = "";
      try {
        instance = echarts.init(offscreen, undefined, {
          renderer: format === "png" ? "canvas" : "svg",
        });
        const merged = { ...buildChartOption(option, theme), animation: false };
        instance.setOption(merged, { notMerge: true });
        // 无动画 + 双 rAF：确保首帧终态已落盘再截图，避免空白/半帧
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        );
        dataUrl = instance.getDataURL({
          type: format,
          pixelRatio: format === "png" ? 2 : 1,
          backgroundColor: "#ffffff",
        });
      } finally {
        instance?.dispose();
        offscreen.remove();
      }

      const ext = format === "png" ? "png" : "svg";
      const targetName = `${fileName}.${ext}`;
      if (isTauri() && workspacePath) {
        // 桌面端：IPC 落盘到工作区 charts/，文件内容哈希后缀防重
        const saved = await saveExportFile(
          workspacePath,
          await toBase64Payload(dataUrl),
          targetName,
        );
        toast.success(
          t("chat.exportSaved", "已导出：{{name}}", {
            name: `charts/${saved.name}`,
          }),
          {
            label: t("chat.openFolder", "打开"),
            onClick: () => {
              openFileLocation(saved.path).catch((err) => {
                console.error("Open export folder failed:", err);
                toast.error(t("chat.openFolderFailed", "无法打开文件夹"));
              });
            },
          },
        );
      } else {
        // 浏览器/dev：直接下载
        const objectUrl = await toObjectUrl(dataUrl);
        try {
          triggerDownload(objectUrl, targetName);
        } finally {
          URL.revokeObjectURL(objectUrl);
        }
      }
    } catch (err) {
      // 导出失败不影响主图展示，仅记录
      console.error("Chart export failed:", err);
      toast.error(t("chat.exportFailed", "图表导出失败，请重试"));
    } finally {
      setSavingFormat(null);
    }
  };

  const exportIcon = (format: ExportFormat) => {
    if (savingFormat === format) {
      return <LoaderCircle size={13} className="spin" aria-hidden />;
    }
    return format === "png" ? (
      <Download size={13} aria-hidden />
    ) : (
      <FileCode2 size={13} aria-hidden />
    );
  };

  const handleExportKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>, format: ExportFormat) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      void exportChart(format);
    }
  };

  return (
    <div className="echarts-block" style={{ height: chartHeight(option) }}>
      {/* 画布容器常驻：失败后 option 变化可无缝重试 */}
      <div ref={containerRef} className="echarts-canvas" />
      {/* 悬浮导出工具条：真实 ECharts 输出，所见即所得 */}
      {!error && (
        <div className="echarts-export-bar">
          <div
            role="button"
            tabIndex={0}
            className="echarts-export-btn"
            title={t("chat.exportPng", "导出 PNG 图片")}
            aria-label={t("chat.exportPng", "导出 PNG 图片")}
            aria-disabled={savingFormat !== null}
            onClick={() => void exportChart("png")}
            onKeyDown={(event) => handleExportKeyDown(event, "png")}
          >
            {exportIcon("png")}
          </div>
          <div
            role="button"
            tabIndex={0}
            className="echarts-export-btn"
            title={t("chat.exportSvg", "导出 SVG 矢量图")}
            aria-label={t("chat.exportSvg", "导出 SVG 矢量图")}
            aria-disabled={savingFormat !== null}
            onClick={() => void exportChart("svg")}
            onKeyDown={(event) => handleExportKeyDown(event, "svg")}
          >
            {exportIcon("svg")}
          </div>
        </div>
      )}
      {error && (
        <div className="echarts-error">
          <AlertTriangle size={14} />
          <span>
            {t("chat.chartRenderFailed", "图表数据格式异常，暂时无法渲染，可重新生成试试")}
          </span>
        </div>
      )}
    </div>
  );
}
