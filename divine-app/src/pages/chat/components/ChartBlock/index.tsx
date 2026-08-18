import { useEffect, useRef } from "react";
import type { ECharts } from "echarts";
import { useTheme } from "@/services/theme";

interface ChartBlockProps {
  option: Record<string, unknown>;
}

import { buildChartOption, chartHeight } from "./chartOptions";

export function ChartBlock({ option }: ChartBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useTheme();

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let disposed = false;
    let frame: number | undefined;
    let observer: ResizeObserver | undefined;
    let chart: ECharts | undefined;

    void import("echarts").then((echarts) => {
      if (disposed) return;
      chart = echarts.init(container);
      frame = requestAnimationFrame(() => {
        chart?.setOption(buildChartOption(option, theme), { notMerge: true });
      });
      observer = new ResizeObserver(() => chart?.resize());
      observer.observe(container);
    });

    return () => {
      disposed = true;
      if (frame !== undefined) cancelAnimationFrame(frame);
      observer?.disconnect();
      chart?.dispose();
    };
  }, [option, theme]);

  return (
    <div
      ref={containerRef}
      className="echarts-block"
      style={{ height: chartHeight(option) }}
    />
  );
}
