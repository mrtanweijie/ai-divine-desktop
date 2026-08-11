import { useEffect, useRef } from "react";
import type { ECharts, EChartsOption } from "echarts";

interface ChartBlockProps {
  option: Record<string, unknown>;
}

const UI_FONT =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif';

const UI_PALETTE = [
  "#7dd3fc",
  "#a5b4fc",
  "#6ee7b7",
  "#f9a8d4",
  "#fde68a",
  "#fca5a5",
  "#c4b5fd",
  "#5eead4",
];

const ITEM_TRIGGER_TYPES = new Set([
  "pie",
  "radar",
  "funnel",
  "gauge",
  "sankey",
  "sunburst",
  "treemap",
  "graph",
  "tree",
  "custom",
]);

const NON_CARTESIAN_TYPES = new Set([
  "pie",
  "radar",
  "funnel",
  "gauge",
  "sankey",
  "sunburst",
  "treemap",
  "graph",
  "tree",
  "parallel",
  "themeRiver",
]);

const FUNCTION_STRING_RE = /^\s*(?:async\s+)?function(?:\s|\()|=>/;

function chartHeight(option: Record<string, unknown>): number {
  const series = Array.isArray(option.series) ? option.series : [];
  const types = series
    .map((item) =>
      item && typeof item === "object" && "type" in item
        ? (item as { type?: unknown }).type
        : undefined
    )
    .filter((type): type is string => typeof type === "string");
  if (types.includes("line")) {
    return 400;
  }
  if (types.includes("graph") || types.includes("tree") || types.includes("sankey")) {
    return 360;
  }
  if (types.includes("radar") || types.includes("funnel")) {
    return 340;
  }
  if (types.includes("pie")) {
    return 280;
  }
  return 320;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function mergeRecord(
  base: Record<string, unknown>,
  override: Record<string, unknown>
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const current = result[key];
    if (isRecord(current) && isRecord(value)) {
      result[key] = mergeRecord(current, value);
    } else {
      result[key] = value;
    }
  }
  return result;
}

function withDefaults(
  target: unknown,
  defaults: Record<string, unknown>
): Record<string, unknown> {
  return mergeRecord(defaults, isRecord(target) ? target : {});
}

function mergeAxis(
  value: unknown,
  defaults: Record<string, unknown>
): unknown {
  if (Array.isArray(value)) {
    return value.map((item) =>
      isRecord(item) ? mergeRecord(defaults, item) : item
    );
  }
  return isRecord(value) ? mergeRecord(defaults, value) : defaults;
}

function decorateSeries(option: Record<string, unknown>): void {
  if (!Array.isArray(option.series)) return;
  option.series = option.series.map((item) => {
    if (!isRecord(item)) return item;
    const next = { ...item };
    const type = typeof item.type === "string" ? item.type : "";
    if (type === "bar") {
      next.itemStyle = withDefaults(next.itemStyle, {
        borderRadius: 4,
        opacity: 0.92,
        borderColor: "rgba(255,255,255,0.12)",
        borderWidth: 1,
      });
      next.barMaxWidth = next.barMaxWidth ?? 30;
    } else if (type === "line") {
      next.smooth = next.smooth ?? true;
      next.symbol = next.symbol ?? "circle";
      next.symbolSize = next.symbolSize ?? 5;
      next.lineStyle = withDefaults(next.lineStyle, { width: 1.5 });
      if (next.areaStyle === undefined) {
        next.areaStyle = { opacity: 0.12 };
      }
    } else if (type === "pie") {
      next.borderColor = next.borderColor ?? "#121517";
      next.borderWidth = next.borderWidth ?? 1.5;
      next.label = withDefaults(next.label, {
        color: "#f2f4f6",
        fontSize: 11,
      });
      next.labelLine = withDefaults(next.labelLine, {
        lineStyle: { color: "rgba(255,255,255,0.18)" },
      });
    }
    return next;
  });
}

function sanitizeFormatters(value: unknown): void {
  if (Array.isArray(value)) {
    for (const item of value) sanitizeFormatters(item);
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (
      (key === "formatter" || key === "valueFormatter") &&
      typeof child === "string" &&
      FUNCTION_STRING_RE.test(child)
    ) {
      delete value[key];
    } else {
      sanitizeFormatters(child);
    }
  }
}

function buildChartOption(option: Record<string, unknown>): EChartsOption {
  const series = Array.isArray(option.series) ? option.series : [];
  const primaryType =
    series.length > 0 &&
    isRecord(series[0]) &&
    typeof series[0].type === "string"
      ? series[0].type
      : "";
  const tooltipTrigger = ITEM_TRIGGER_TYPES.has(primaryType) ? "item" : "axis";

  const theme: Record<string, unknown> = {
    color: UI_PALETTE,
    textStyle: {
      fontFamily: UI_FONT,
      color: "#a4adba",
    },
    title: {
      textStyle: {
        fontFamily: UI_FONT,
        color: "#f2f4f6",
        fontSize: 13,
        fontWeight: 600,
      },
    },
    legend: {
      top: 8,
      right: 12,
      icon: "roundRect",
      itemWidth: 10,
      itemHeight: 6,
      itemGap: 12,
      textStyle: {
        fontFamily: UI_FONT,
        color: "#a4adba",
        fontSize: 11,
      },
    },
    tooltip: {
      backgroundColor: "rgba(18,21,23,0.96)",
      borderColor: "rgba(255,255,255,0.12)",
      borderWidth: 1,
      padding: [8, 10],
      textStyle: {
        fontFamily: UI_FONT,
        color: "#f2f4f6",
        fontSize: 12,
      },
      extraCssText:
        "border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,0.35);",
    },
    grid: {
      left: 12,
      right: 16,
      top: 42,
      bottom: 8,
      containLabel: true,
    },
    xAxis: {
      axisLine: {
        lineStyle: { color: "rgba(255,255,255,0.14)" },
      },
      axisTick: { show: false },
      axisLabel: {
        color: "#a4adba",
        fontFamily: UI_FONT,
        fontSize: 11,
      },
      splitLine: { show: false },
    },
    yAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: "#6f7783",
        fontFamily: UI_FONT,
        fontSize: 11,
      },
      splitLine: {
        lineStyle: { color: "rgba(255,255,255,0.06)" },
      },
    },
  };

  const merged = mergeRecord(theme, option);
  const usesCartesianAxis =
    primaryType === "" || !NON_CARTESIAN_TYPES.has(primaryType);
  if (usesCartesianAxis) {
    if (Array.isArray(option.xAxis) || !isRecord(option.xAxis)) {
      merged.xAxis = mergeAxis(
        option.xAxis,
        theme.xAxis as Record<string, unknown>
      );
    }
    if (Array.isArray(option.yAxis) || !isRecord(option.yAxis)) {
      merged.yAxis = mergeAxis(
        option.yAxis,
        theme.yAxis as Record<string, unknown>
      );
    }
  } else {
    if (option.xAxis === undefined) delete merged.xAxis;
    if (option.yAxis === undefined) delete merged.yAxis;
    if (option.grid === undefined) delete merged.grid;
  }
  if (isRecord(merged.tooltip) && merged.tooltip.trigger === undefined) {
    merged.tooltip = {
      ...merged.tooltip,
      trigger: tooltipTrigger,
    };
  }
  if (primaryType === "funnel" && isRecord(merged.legend)) {
    merged.legend = withDefaults(merged.legend, {
      orient: "vertical",
      top: 16,
      right: 12,
      bottom: "auto",
      left: "auto",
    });
  }
  sanitizeFormatters(merged);
  decorateSeries(merged);
  return merged as unknown as EChartsOption;
}

export function ChartBlock({ option }: ChartBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);

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
        chart?.setOption(buildChartOption(option), { notMerge: true });
        chart?.resize();
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
  }, [option]);

  return (
    <div
      ref={containerRef}
      className="echarts-block"
      style={{ height: chartHeight(option) }}
    />
  );
}
