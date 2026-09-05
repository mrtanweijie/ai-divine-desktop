import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import type { ECharts } from "echarts";
import { useTheme } from "@/services/theme";

interface ChartBlockProps {
  option: Record<string, unknown>;
}

import { buildChartOption, chartHeight } from "./chartOptions";

export function ChartBlock({ option }: ChartBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useTheme();
  const { t } = useTranslation();
  // 渲染失败（数据损坏/option 非法）→ 覆盖层提示，而非白屏
  const [error, setError] = useState(false);

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
    };
  }, [option, theme]);

  return (
    <div className="echarts-block" style={{ height: chartHeight(option) }}>
      {/* 画布容器常驻：失败后 option 变化可无缝重试 */}
      <div ref={containerRef} className="echarts-canvas" />
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
