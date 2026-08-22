// ECharts option normalization and theme decoration, kept separate from React.
import type { EChartsOption } from "echarts";

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

// Pie charts with more slices than this keep hidden labels (a bare ring is
// cleaner than a label salad); smaller ones get per-segment indicator text.
const MAX_PIE_LABEL_SLICES = 8;

// When a pie also has a title and/or bottom caption, cap the ring's outer
// radius (percent of the smaller canvas side) so the ring doesn't crowd the
// title — ECharts scales the ring with the canvas height, which otherwise
// pushes a big donut up into the title area.
const MAX_PIE_RADIUS_PCT = 62;

// Max thickness of the donut band (percent of the smaller canvas side). A
// plain donut look means a thin ring, not a thick torus.
const MAX_PIE_BAND_PCT = 16;

/**
 * Normalize a pie series to the plain donut look: thin ring, slices that butt
 * against each other (no white gap, no rounded ends). The outer radius is
 * capped at MAX_PIE_RADIUS_PCT when a title/caption is present, and the band
 * is thinned to at most MAX_PIE_BAND_PCT by raising the inner radius.
 */
function normalizePieStyle(
  series: Record<string, unknown>,
  hasContent: boolean
): void {
  const itemStyle = isRecord(series.itemStyle) ? { ...series.itemStyle } : {};
  itemStyle.borderRadius = 0;
  itemStyle.borderWidth = 0;
  itemStyle.borderColor = "transparent";
  series.itemStyle = itemStyle;

  const radius = series.radius;
  if (typeof radius === "string") {
    const percent = Number(radius.replace("%", ""));
    if (!Number.isNaN(percent) && hasContent && percent > MAX_PIE_RADIUS_PCT) {
      series.radius = `${MAX_PIE_RADIUS_PCT}%`;
    }
    return;
  }
  if (!Array.isArray(radius) || radius.length < 2) return;
  const [innerRaw, outerRaw] = radius;
  if (typeof innerRaw !== "string" || typeof outerRaw !== "string") return;
  let innerPercent = Number(innerRaw.replace("%", ""));
  let outerPercent = Number(outerRaw.replace("%", ""));
  if (Number.isNaN(innerPercent) || Number.isNaN(outerPercent)) return;
  if (hasContent && outerPercent > MAX_PIE_RADIUS_PCT) {
    const scale = MAX_PIE_RADIUS_PCT / outerPercent;
    outerPercent = MAX_PIE_RADIUS_PCT;
    innerPercent *= scale;
  }
  const minInner = outerPercent - MAX_PIE_BAND_PCT;
  if (innerPercent < minInner) innerPercent = minInner;
  const round1 = (value: number) => Math.round(value * 10) / 10;
  series.radius = [
    `${round1(innerPercent)}%`,
    `${round1(outerPercent)}%`,
  ];
}

type ChartTheme = "dark" | "light";

interface ChartPalette {
  text: string;
  muted: string;
  label: string;
  labelBg: string;
  border: string;
  axisLine: string;
  splitLine: string;
  tooltipBg: string;
  tooltipBorder: string;
}

const CHART_PALETTES: Record<ChartTheme, ChartPalette> = {
  dark: {
    text: "#e8ecf1",
    muted: "#a4adba",
    label: "#e8ecf1",
    labelBg: "rgba(15, 18, 21, 0.78)",
    border: "#121517",
    axisLine: "rgba(255,255,255,0.12)",
    splitLine: "rgba(255,255,255,0.07)",
    tooltipBg: "rgba(18,21,23,0.96)",
    tooltipBorder: "rgba(255,255,255,0.12)",
  },
  light: {
    text: "#1f2937",
    muted: "#5b6472",
    label: "#1f2937",
    labelBg: "rgba(255,255,255,0.92)",
    border: "#e5e7eb",
    axisLine: "rgba(15,23,42,0.25)",
    splitLine: "rgba(15,23,42,0.10)",
    tooltipBg: "rgba(255,255,255,0.96)",
    tooltipBorder: "rgba(15,23,42,0.14)",
  },
};

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

function primarySeriesType(option: Record<string, unknown>): string {
  const series = Array.isArray(option.series) ? option.series : [];
  for (const item of series) {
    if (isRecord(item) && typeof item.type === "string") return item.type;
  }
  return "";
}

/** Estimate a stable chart height from the dominant series type. */
export function chartHeight(option: Record<string, unknown>): number {
  const primaryType = primarySeriesType(option);
  const types = Array.isArray(option.series)
    ? option.series
        .map((item) =>
          isRecord(item) && typeof item.type === "string" ? item.type : ""
        )
        .filter(Boolean)
    : [];
  const baseHeight =
    types.includes("candlestick")
      ? 480
      : types.includes("line")
      ? 400
      : types.includes("graph") ||
        types.includes("tree") ||
        types.includes("sankey")
        ? 360
        : types.includes("radar") || types.includes("funnel")
          ? 340
          : types.includes("pie")
            ? 280
            : 320;

  // Pie keeps its title now (a pie without its subject title looks bare), so
  // count the title height for it as well; only funnel drops the title.
  const showTitle = primaryType !== "funnel";
  const titleExtra = showTitle ? titleHeight(option) : 0;
  const legendExtra = legendHeight(option);
  const bottomCaption = bottomCaptionHeight(option);
  let height = baseHeight;
  if (primaryType && !NON_CARTESIAN_TYPES.has(primaryType)) {
    if (isHorizontalCartesian(option)) {
      const categories = Math.max(
        axisDataCount(option.yAxis),
        axisDataCount(option.xAxis)
      );
      height = Math.max(
        baseHeight,
        240 + titleExtra + legendExtra + categories * 34
      );
    } else {
      height = Math.max(baseHeight, 300 + titleExtra + legendExtra);
    }
  } else {
    height = baseHeight + titleExtra + legendExtra;
  }
  return Math.min(Math.max(height + bottomCaption, 240), 900);
}

function firstAxis(value: unknown): Record<string, unknown> | null {
  if (Array.isArray(value)) {
    return value.find(isRecord) ?? null;
  }
  return isRecord(value) ? value : null;
}

function axisDataCount(value: unknown): number {
  const data = firstAxis(value)?.data;
  return Array.isArray(data) ? data.length : 0;
}

function titleHeight(option: Record<string, unknown>): number {
  const title = option.title;
  if (!isRecord(title)) return 0;
  const hasText = typeof title.text === "string" && title.text.length > 0;
  const hasSubtext =
    typeof title.subtext === "string" && title.subtext.length > 0;
  if (!hasText && !hasSubtext) return 0;
  return hasSubtext ? 56 : 36;
}

function legendHeight(option: Record<string, unknown>): number {
  const legend = option.legend;
  if (!isRecord(legend) || legend.show === false) return 0;
  return 24;
}

function isHorizontalCartesian(option: Record<string, unknown>): boolean {
  const yAxis = firstAxis(option.yAxis);
  if (yAxis?.type === "category") return true;
  const xAxis = firstAxis(option.xAxis);
  if (xAxis?.type === "category") return false;
  return false;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * True when a component (title/graphic) is anchored to the bottom edge:
 * a concrete `bottom` offset with no overriding `top` offset. LLMs commonly
 * annotate charts with a "数据来源：…" line at the bottom this way, and ECharts
 * lays such captions out independently of the grid/series, so they overlap the
 * plot and look covered by the chart unless space is reserved.
 */
function isBottomAnchored(value: Record<string, unknown>): boolean {
  const bottom = value.bottom;
  if (bottom === undefined || bottom === null || bottom === "auto") return false;
  const top = value.top;
  if (top !== undefined && top !== null && top !== "auto") return false;
  return true;
}

function titleHasText(title: Record<string, unknown>): boolean {
  return (
    (typeof title.text === "string" && title.text.length > 0) ||
    (typeof title.subtext === "string" && title.subtext.length > 0)
  );
}

/** Height (px) reserved at the canvas bottom by bottom-anchored captions. */
function bottomCaptionHeight(option: Record<string, unknown>): number {
  let total = 0;
  const titles = Array.isArray(option.title)
    ? option.title
    : isRecord(option.title)
      ? [option.title]
      : [];
  for (const title of titles) {
    if (!isRecord(title) || !isBottomAnchored(title) || !titleHasText(title)) {
      continue;
    }
    const hasSubtext =
      typeof title.subtext === "string" && title.subtext.length > 0;
    total += hasSubtext ? 36 : 24;
  }
  const graphic = option.graphic;
  const graphics = Array.isArray(graphic)
    ? graphic
    : isRecord(graphic)
      ? Array.isArray(graphic.elements)
        ? graphic.elements
        : [graphic]
      : [];
  for (const g of graphics) {
    if (!isRecord(g) || g.type !== "text" || !isBottomAnchored(g)) continue;
    const style = isRecord(g.style) ? g.style : {};
    const fontSize = typeof style.fontSize === "number" ? style.fontSize : 12;
    const text = typeof style.text === "string" ? style.text : "";
    const lineCount = text.length > 0 ? text.split("\n").length : 1;
    total += Math.round(fontSize * 1.5) * lineCount;
  }
  return total;
}

/**
 * Give multi-line graphic captions ("数据来源：…") a comfortable line height
 * so wrapped lines don't stick together (ECharts' default is tight).
 */
function decorateGraphicCaptions(option: Record<string, unknown>): void {
  const graphic = option.graphic;
  const items = Array.isArray(graphic)
    ? graphic
    : isRecord(graphic)
      ? Array.isArray(graphic.elements)
        ? graphic.elements
        : [graphic]
      : [];
  for (const g of items) {
    if (!isRecord(g) || g.type !== "text") continue;
    const style = isRecord(g.style) ? { ...g.style } : {};
    if (style.lineHeight === undefined) {
      const fontSize = typeof style.fontSize === "number" ? style.fontSize : 12;
      style.lineHeight = Math.round(fontSize * 1.5);
    }
    g.style = style;
  }
}

/**
 * Replace the title with only bottom-anchored caption titles. Used for
 * pie/funnel where the default theme drops the title, so a bottom
 * "数据来源：…" caption must be kept instead of thrown away.
 */
function keepBottomCaptions(merged: Record<string, unknown>): void {
  const titles = Array.isArray(merged.title)
    ? merged.title
    : isRecord(merged.title)
      ? [merged.title]
      : [];
  const captions = titles.filter(
    (title): title is Record<string, unknown> =>
      isRecord(title) && isBottomAnchored(title) && titleHasText(title)
  );
  if (captions.length > 0) {
    merged.title = captions.length === 1 ? captions[0] : captions;
  } else {
    delete merged.title;
  }
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

function decorateSeries(
  option: Record<string, unknown>,
  palette: ChartPalette
): void {
  if (!Array.isArray(option.series)) return;
  option.series = option.series.map((item) => {
    if (!isRecord(item)) return item;
    const next = { ...item };
    const type = typeof item.type === "string" ? item.type : "";
    if (type === "bar") {
      const itemStyle = withDefaults(next.itemStyle, {
        borderRadius: 4,
        opacity: 0.92,
      });
      itemStyle.borderColor = "transparent";
      itemStyle.borderWidth = 0;
      next.itemStyle = itemStyle;
      const hasSecondaryXAxis =
        Array.isArray(option.xAxis) && option.xAxis.length > 1;
      const volumeLike =
        /成交量|成交额|volume/i.test(String(next.name ?? "")) ||
        (hasSecondaryXAxis &&
          (next.xAxisIndex === 1 || next.yAxisIndex === 1));
      if (isHorizontalCartesian(option)) {
        next.barWidth = "70%";
        next.barCategoryGap = "10%";
      } else if (volumeLike) {
        next.barMaxWidth = 10;
        next.barCategoryGap = next.barCategoryGap ?? "10%";
        next.barGap = next.barGap ?? "15%";
      } else {
        next.barMaxWidth = next.barMaxWidth ?? 30;
        next.barCategoryGap = next.barCategoryGap ?? "10%";
        next.barGap = next.barGap ?? "15%";
      }
      const label = isRecord(next.label) ? { ...next.label } : {};
      if (volumeLike) {
        label.show = false;
      } else {
        label.show = true;
        label.position = isHorizontalCartesian(option) ? "right" : "top";
        label.color = label.color ?? palette.label;
        label.fontSize = label.fontSize ?? 11;
        label.fontWeight = label.fontWeight ?? 600;
      }
      next.label = label;
      if (isHorizontalCartesian(option)) {
        const emphasis = isRecord(next.emphasis) ? { ...next.emphasis } : {};
        const emphasisStyle = isRecord(emphasis.itemStyle)
          ? { ...emphasis.itemStyle }
          : {};
        emphasisStyle.borderRadius = 4;
        emphasis.itemStyle = emphasisStyle;
        next.emphasis = emphasis;
        if (isRecord(option.tooltip)) {
          option.tooltip = {
            ...option.tooltip,
            axisPointer: {
              type: "line",
              lineStyle: { color: "rgba(255,255,255,0.18)" },
            },
          };
        }
      }
    } else if (type === "line") {
      next.smooth = next.smooth ?? true;
      next.symbol = next.symbol ?? "circle";
      next.symbolSize = next.symbolSize ?? 5;
      next.lineStyle = withDefaults(next.lineStyle, { width: 1.5 });
      const label = isRecord(next.label) ? { ...next.label } : {};
      if (label.show !== false) {
        label.color = palette.label;
        label.fontSize = label.fontSize ?? 11;
        label.fontWeight = label.fontWeight ?? 600;
        label.backgroundColor = palette.labelBg;
        label.borderRadius = 4;
        label.padding = [2, 5];
        label.shadowBlur = 4;
        label.shadowColor =
          palette.border === "#121517"
            ? "rgba(0, 0, 0, 0.45)"
            : "rgba(15, 23, 42, 0.18)";
      }
      next.label = label;
      if (next.areaStyle === undefined) {
        next.areaStyle = { opacity: 0.12 };
      }
    } else if (type === "pie") {
      // Slice colors come from the LLM's itemStyle (already normalized to the
      // plain look — no borders/rounding — in buildChartOption).
      const itemStyle = isRecord(next.itemStyle) ? { ...next.itemStyle } : {};
      next.itemStyle = itemStyle;
      const label = isRecord(next.label) ? { ...next.label } : {};
      label.color = palette.label;
      label.fontSize = label.fontSize ?? 11;
      next.label = label;
      const labelLine = isRecord(next.labelLine) ? { ...next.labelLine } : {};
      const labelLineStyle = isRecord(labelLine.lineStyle)
        ? { ...labelLine.lineStyle }
        : {};
      labelLineStyle.color = palette.axisLine;
      labelLine.lineStyle = labelLineStyle;
      next.labelLine = labelLine;
      if (isRecord(next.emphasis)) {
        const emphasis = { ...next.emphasis };
        const emphasisLabel = isRecord(emphasis.label)
          ? { ...emphasis.label }
          : {};
        emphasisLabel.color = palette.label;
        emphasis.label = emphasisLabel;
        next.emphasis = emphasis;
      }
    } else if (type === "treemap") {
      const itemStyle = isRecord(next.itemStyle) ? { ...next.itemStyle } : {};
      itemStyle.borderColor = palette.border;
      next.itemStyle = itemStyle;
      if (Array.isArray(next.levels)) {
        next.levels = next.levels.map((level) => {
          if (!isRecord(level)) return level;
          const nextLevel = { ...level };
          const levelStyle = isRecord(nextLevel.itemStyle)
            ? { ...nextLevel.itemStyle }
            : {};
          levelStyle.borderColor = palette.border;
          nextLevel.itemStyle = levelStyle;
          return nextLevel;
        });
      }
      const breadcrumb = isRecord(next.breadcrumb) ? next.breadcrumb : {};
      next.breadcrumb = {
        ...breadcrumb,
        itemStyle: withDefaults(breadcrumb.itemStyle, {
          color: palette.border,
          borderColor: palette.axisLine,
          borderWidth: 1,
          textStyle: {
            color: palette.muted,
            fontFamily: UI_FONT,
            fontSize: 11,
          },
        }),
      };
    } else if (type === "funnel") {
      const itemStyle = isRecord(next.itemStyle) ? { ...next.itemStyle } : {};
      itemStyle.borderColor = "transparent";
      itemStyle.borderWidth = 0;
      next.itemStyle = itemStyle;
    }
    return next;
  });
}

function decorateRadar(
  option: Record<string, unknown>,
  palette: ChartPalette
): void {
  const applyRadar = (radar: Record<string, unknown>) => {
    radar.axisName = withDefaults(radar.axisName, {
      color: palette.muted,
      fontFamily: UI_FONT,
      fontSize: 11,
    });
    radar.axisLabel = withDefaults(radar.axisLabel, {
      color: palette.muted,
      fontFamily: UI_FONT,
      fontSize: 10,
    });
    radar.axisLine = withDefaults(radar.axisLine, {
      lineStyle: { color: palette.axisLine },
    });
    radar.splitLine = withDefaults(radar.splitLine, {
      lineStyle: { color: palette.splitLine },
    });
    const splitArea = isRecord(radar.splitArea) ? { ...radar.splitArea } : {};
    splitArea.show = false;
    radar.splitArea = splitArea;
  };
  if (Array.isArray(option.radar)) {
    for (const radar of option.radar) {
      if (isRecord(radar)) applyRadar(radar);
    }
  } else if (isRecord(option.radar)) {
    applyRadar(option.radar);
  }
}

function decorateAxes(
  option: Record<string, unknown>,
  palette: ChartPalette
): void {
  const applyAxis = (axis: Record<string, unknown>) => {
    axis.splitArea = {
      ...(isRecord(axis.splitArea) ? axis.splitArea : {}),
      show: false,
    };
    const label = isRecord(axis.axisLabel) ? { ...axis.axisLabel } : {};
    label.color = palette.muted;
    label.fontFamily = UI_FONT;
    label.fontSize = label.fontSize ?? 11;
    axis.axisLabel = label;
    const nameStyle = isRecord(axis.nameTextStyle)
      ? { ...axis.nameTextStyle }
      : {};
    nameStyle.color = palette.muted;
    nameStyle.fontFamily = UI_FONT;
    axis.nameTextStyle = nameStyle;
    const axisLine = isRecord(axis.axisLine) ? { ...axis.axisLine } : {};
    const axisLineStyle = isRecord(axisLine.lineStyle)
      ? { ...axisLine.lineStyle }
      : {};
    axisLineStyle.color = palette.axisLine;
    axisLine.lineStyle = axisLineStyle;
    axis.axisLine = axisLine;
    const splitLine = isRecord(axis.splitLine) ? { ...axis.splitLine } : {};
    const splitLineStyle = isRecord(splitLine.lineStyle)
      ? { ...splitLine.lineStyle }
      : {};
    splitLineStyle.color = palette.splitLine;
    splitLine.lineStyle = splitLineStyle;
    axis.splitLine = splitLine;
  };
  for (const key of ["xAxis", "yAxis"] as const) {
    const value = option[key];
    if (Array.isArray(value)) {
      for (const axis of value) {
        if (isRecord(axis)) applyAxis(axis);
      }
    } else if (isRecord(value)) {
      applyAxis(value);
    }
  }
}

function decorateReadableText(
  option: Record<string, unknown>,
  palette: ChartPalette
): void {
  const primaryType = primarySeriesType(option);
  const nonCartesian =
    primaryType !== "" && NON_CARTESIAN_TYPES.has(primaryType);
  if (isRecord(option.legend)) {
    const textStyle = isRecord(option.legend.textStyle)
      ? { ...option.legend.textStyle }
      : {};
    textStyle.color = palette.muted;
    textStyle.fontFamily = UI_FONT;
    textStyle.fontSize = textStyle.fontSize ?? 11;
    option.legend.textStyle = textStyle;
  }
  if (isRecord(option.title)) {
    const textStyle = isRecord(option.title.textStyle)
      ? { ...option.title.textStyle }
      : {};
    textStyle.color = palette.muted;
    textStyle.fontFamily = UI_FONT;
    option.title.textStyle = textStyle;
    // A bottom-anchored caption must stay at the bottom; do not relocate it
    // to the top just because a legend is present. Non-cartesian charts
    // (pie/radar/…) keep the LLM's own title/legend placement.
    if (
      !nonCartesian &&
      isRecord(option.legend) &&
      option.legend.show !== false &&
      !isBottomAnchored(option.title)
    ) {
      option.title = { ...option.title, left: 16, top: 10 };
      option.legend = { ...option.legend, top: 48, right: 12 };
    }
  } else if (Array.isArray(option.title)) {
    for (const title of option.title) {
      if (!isRecord(title)) continue;
      const textStyle = isRecord(title.textStyle)
        ? { ...title.textStyle }
        : {};
      textStyle.color = palette.muted;
      textStyle.fontFamily = UI_FONT;
      title.textStyle = textStyle;
    }
  }
  if (isRecord(option.tooltip)) {
    const tooltip = { ...option.tooltip };
    const textStyle = isRecord(option.tooltip.textStyle)
      ? { ...option.tooltip.textStyle }
      : {};
    textStyle.color = palette.text;
    textStyle.fontFamily = UI_FONT;
    tooltip.textStyle = textStyle;
    const extraCss =
      typeof tooltip.extraCssText === "string" ? tooltip.extraCssText : "";
    tooltip.extraCssText = /border-radius/i.test(extraCss)
      ? extraCss
      : `${extraCss ? `${extraCss};` : ""}border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,0.35);`;
    if (isRecord(tooltip.axisPointer)) {
      const pointer = { ...tooltip.axisPointer };
      const shadowStyle = isRecord(pointer.shadowStyle)
        ? { ...pointer.shadowStyle }
        : {};
      shadowStyle.borderRadius = 4;
      pointer.shadowStyle = shadowStyle;
      tooltip.axisPointer = pointer;
    }
    option.tooltip = tooltip;
  }
}

function movingAverage(values: number[], dayCount: number): (number | string)[] {
  const result: (number | string)[] = [];
  for (let i = 0; i < values.length; i++) {
    if (i < dayCount) {
      result.push("-");
      continue;
    }
    let sum = 0;
    for (let j = 0; j < dayCount; j++) {
      sum += values[i - j];
    }
    result.push(Number((sum / dayCount).toFixed(3)));
  }
  return result;
}

/**
 * Normalize candlestick multi-grid axes: trim spurious xAxis entries that
 * LLMs commonly mistake for yAxis configs, and ensure yAxis is a 2-element
 * array when the volume series references yAxisIndex: 1.
 */
function fixCandlestickAxes(
  option: Record<string, unknown>,
  yAxisDefaults: Record<string, unknown>
): void {
  // 1. Trim xAxis: keep only the first 2 real date/category axes.
  //    LLMs often append yAxis configs (scale, splitArea, gridIndex: 1) to
  //    xAxis when generating candlestick charts.
  const series = Array.isArray(option.series) ? option.series : [];
  const hasVolume = series.some(
    (item) =>
      isRecord(item) &&
      item.type === "bar" &&
      (item.xAxisIndex === 1 || item.yAxisIndex === 1)
  );
  const grids = Array.isArray(option.grid)
    ? option.grid
    : isRecord(option.grid)
      ? [option.grid]
      : [];

  if (Array.isArray(option.xAxis) && option.xAxis.length > 2) {
    // Keep only the first 2 xAxis entries (the real category axes for
    // candlestick and volume). Entries beyond index 1 that lack "data" or
    // "type: category" are almost certainly misplaced yAxis configs.
    option.xAxis = option.xAxis.slice(0, 2);
  }

  // 2. Build a proper yAxis array when the volume series needs yAxisIndex: 1.
  if (hasVolume && grids.length >= 2) {
    const raw = option.yAxis;
    if (!Array.isArray(raw)) {
      // yAxis is a single object (or undefined/missing after merge): build
      // the standard 2-element array for a candlestick + volume layout.
      const priceAxis = isRecord(raw)
        ? { ...raw, gridIndex: 0 }
        : { gridIndex: 0 };
      const volumeAxis: Record<string, unknown> = {
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      };
      option.yAxis = [
        mergeRecord(yAxisDefaults, priceAxis),
        mergeRecord(yAxisDefaults, volumeAxis),
      ];
    } else if (raw.length === 1) {
      // yAxis has one entry but volume needs index 1: append the volume axis.
      option.yAxis = [
        raw[0],
        mergeRecord(yAxisDefaults, {
          gridIndex: 1,
          splitNumber: 2,
          axisLabel: { show: false },
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { show: false },
        }),
      ];
    }
    // raw.length >= 2: yAxis already correct, leave it untouched.
  }
}

function decorateCandlestick(
  option: Record<string, unknown>,
  palette: ChartPalette
): void {
  const upColor = "#00da3c";
  const downColor = "#ec0000";
  const series = Array.isArray(option.series)
    ? option.series.map((item) => (isRecord(item) ? { ...item } : item))
    : [];
  option.series = series;

  const candle = series.find(
    (item) => isRecord(item) && item.type === "candlestick"
  );
  const volume = series.find(
    (item) =>
      isRecord(item) &&
      item.type === "bar" &&
      (item.xAxisIndex === 1 ||
        item.yAxisIndex === 1 ||
        /成交量|成交额|volume/i.test(String(item.name ?? "")))
  );

  if (isRecord(candle)) {
    candle.itemStyle = {
      ...(isRecord(candle.itemStyle) ? candle.itemStyle : {}),
      color: upColor,
      color0: downColor,
      borderColor: upColor,
      borderColor0: downColor,
    };

    const rawValues = Array.isArray(candle.data)
      ? candle.data.filter((value): value is unknown[] => Array.isArray(value))
      : [];
    const closes = rawValues.map((value) => Number(value[1]));
    if (closes.some(Number.isFinite)) {
      const existingNames = new Set(
        series
          .map((item) => (isRecord(item) ? item.name : undefined))
          .filter((name): name is string => typeof name === "string")
      );
      const maSeries = [5, 10, 20, 30]
        .filter((day) => !existingNames.has(`MA${day}`))
        .map((day) => ({
          name: `MA${day}`,
          type: "line",
          data: movingAverage(closes, day),
          smooth: true,
          symbol: "none",
          areaStyle: { opacity: 0 },
          lineStyle: { width: 1, opacity: 0.5 },
        }));
      if (maSeries.length > 0) {
        series.splice(series.indexOf(candle) + 1, 0, ...maSeries);
      }
    }

    if (isRecord(option.legend)) {
      const legendNames = [
        ...(typeof candle.name === "string" ? [candle.name] : []),
        ...[5, 10, 20, 30].map((day) => `MA${day}`),
      ];
      option.legend = {
        ...option.legend,
        bottom: 10,
        left: "center",
        top: "auto",
        right: "auto",
        data: legendNames,
      };
    }
  }

  if (isRecord(volume)) {
    if (
      Array.isArray(volume.data) &&
      volume.data.every((value) => typeof value === "number") &&
      isRecord(candle) &&
      Array.isArray(candle.data)
    ) {
      const opens = candle.data
        .filter((value): value is unknown[] => Array.isArray(value))
        .map((value) => Number(value[0]));
      const closes = candle.data
        .filter((value): value is unknown[] => Array.isArray(value))
        .map((value) => Number(value[1]));
      volume.data = volume.data.map((value, index) => [
        index,
        Number(value),
        closes[index] >= opens[index] ? 1 : -1,
      ]);
      const volumeIndex = series.indexOf(volume);
      if (!isRecord(option.visualMap)) {
        option.visualMap = {
          show: false,
          seriesIndex: volumeIndex,
          dimension: 2,
          pieces: [
            { value: 1, color: upColor },
            { value: -1, color: downColor },
          ],
        };
      }
    }
  }

  if (Array.isArray(option.dataZoom)) {
    for (const zoom of option.dataZoom) {
      if (isRecord(zoom) && zoom.type === "slider") {
        zoom.top = "85%";
        zoom.bottom = "auto";
      }
    }
  }
  const grids = Array.isArray(option.grid)
    ? option.grid
    : isRecord(option.grid)
      ? [option.grid]
      : [];
  if (grids.length > 0 && isRecord(grids[0])) {
    grids[0] = { ...grids[0], height: "50%" };
  }
  if (grids.length > 1 && isRecord(grids[1])) {
    grids[1] = { ...grids[1], top: "63%", height: "16%" };
  }
  if (Array.isArray(option.grid)) {
    option.grid = grids;
  } else if (grids[0]) {
    option.grid = grids[0];
  }
  if (!isRecord(option.axisPointer)) {
    option.axisPointer = {
      link: [{ xAxisIndex: "all" }],
      label: { backgroundColor: palette.muted },
    };
  }
}

// ECharts 6.x 的 globalBackwardCompat 递归遍历 option 子属性时，会对
// series[].data 里的原始值（number/string）调用 prop in value —— 对非 Object
// 值使用 in 运算符会 TypeError: "option is not an Object"。
// 修复：把原始值包装成 {value: N}（ECharts 推荐格式，行为等价）。
function normalizeSeriesData(option: Record<string, unknown>): void {
  if (!Array.isArray(option.series)) return;
  for (const s of option.series) {
    if (!isRecord(s) || !Array.isArray(s.data)) continue;
    s.data = s.data.map((d: unknown) =>
      typeof d === "number" || typeof d === "string" || typeof d === "boolean"
        ? { value: d }
        : d
    );
  }
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

/**
 * Merge AI-provided ECharts options with theme defaults, normalize axes and
 * series, and strip unsafe function string formatters.
 */
export function buildChartOption(
  option: Record<string, unknown>,
  theme: ChartTheme
): EChartsOption {
  const palette = CHART_PALETTES[theme];
  const series = Array.isArray(option.series) ? option.series : [];
  const primaryType =
    series.length > 0 &&
    isRecord(series[0]) &&
    typeof series[0].type === "string"
      ? series[0].type
      : "";
  const tooltipTrigger = ITEM_TRIGGER_TYPES.has(primaryType) ? "item" : "axis";
  const bottomCaption = bottomCaptionHeight(option);

  const themeBase: Record<string, unknown> = {
    color: UI_PALETTE,
    textStyle: {
      fontFamily: UI_FONT,
      color: palette.muted,
    },
    title: {
      textStyle: {
        fontFamily: UI_FONT,
        color: palette.text,
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
        color: palette.muted,
        fontSize: 11,
      },
    },
    tooltip: {
      backgroundColor: palette.tooltipBg,
      borderColor: palette.tooltipBorder,
      borderWidth: 1,
      padding: [8, 10],
      textStyle: {
        fontFamily: UI_FONT,
        color: palette.text,
        fontSize: 12,
      },
      extraCssText:
        theme === "light"
          ? "border-radius:8px;box-shadow:0 8px 24px rgba(15,23,42,0.12);"
          : "border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,0.35);",
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
        lineStyle: { color: palette.axisLine },
      },
      axisTick: { show: false },
      axisLabel: {
        color: palette.muted,
        fontFamily: UI_FONT,
        fontSize: 11,
      },
      splitLine: { show: false },
    },
    yAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: palette.muted,
        fontFamily: UI_FONT,
        fontSize: 11,
      },
      splitLine: {
        lineStyle: { color: palette.splitLine },
      },
    },
  };

  // LLM 常把 title 写成字符串而非 {text:"..."} 对象，ECharts 6.x 的
  // globalBackwardCompat 会遍历 COMPATITABLE_COMPONENTS（含 title）对每个
  // 组件调用 compatLayoutProperties(option) → `prop in option` 对非对象崩溃。
  // 这里把字符串/数字 title 规范化为 {text:...} 对象，覆盖到 themeBase 之前。
  if (typeof option.title === "string" || typeof option.title === "number") {
    option = { ...option, title: { text: String(option.title) } };
  }

  decorateGraphicCaptions(option);

  const merged = mergeRecord(themeBase, option);
  // LLMs often hardcode `backgroundColor: "#ffffff"`, which paints the canvas
  // white and breaks the dark theme. Drop it: the canvas stays transparent and
  // the themed container background (--color-surface) shows through.
  delete merged.backgroundColor;
  decorateReadableText(merged, palette);
  const usesCartesianAxis =
    primaryType === "" || !NON_CARTESIAN_TYPES.has(primaryType);
  if (usesCartesianAxis) {
    if (
      isRecord(merged.title) &&
      isRecord(merged.legend) &&
      merged.legend.show !== false &&
      isRecord(merged.grid)
    ) {
      merged.grid = { ...merged.grid, top: 96 };
    }
    if (Array.isArray(option.xAxis) || !isRecord(option.xAxis)) {
      merged.xAxis = mergeAxis(
        option.xAxis,
        themeBase.xAxis as Record<string, unknown>
      );
    }
    if (Array.isArray(option.yAxis) || !isRecord(option.yAxis)) {
      merged.yAxis = mergeAxis(
        option.yAxis,
        themeBase.yAxis as Record<string, unknown>
      );
    }
    decorateAxes(merged, palette);
    if (primaryType === "candlestick") {
      // LLMs sometimes put yAxis configs into xAxis (e.g. 4 xAxis entries
      // where the last 2 are actually volume/pricing yAxis configs). Trim
      // xAxis to the 2 real date axes and build a proper 2-element yAxis
      // array when the volume series references yAxisIndex: 1 but yAxis is
      // missing or only a single object.
      fixCandlestickAxes(merged, themeBase.yAxis as Record<string, unknown>);
      decorateCandlestick(merged, palette);
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
  if (primaryType === "pie") {
    const firstSeries = series[0];
    const radius =
      isRecord(firstSeries) && Array.isArray(firstSeries.radius)
        ? firstSeries.radius
        : null;
    if (radius && radius.length > 1 && isRecord(merged.legend)) {
      merged.legend = {
        ...merged.legend,
        orient: "vertical",
        left: 16,
        top: "middle",
        right: "auto",
        bottom: "auto",
      };
    }
    // LLMs often hide pie labels ("label.show: false" plus a legend), leaving
    // a bare ring. For smaller pies, re-enable classic outside labels with
    // leader lines (text sits beside each slice, not on the ring) and drop the
    // legend — the "名称 百分比" labels carry the same info and the legend
    // would collide with the leader lines.
    if (
      isRecord(firstSeries) &&
      isRecord(firstSeries.label) &&
      firstSeries.label.show === false
    ) {
      const dataCount = Array.isArray(firstSeries.data)
        ? firstSeries.data.length
        : 0;
      if (dataCount > 0 && dataCount <= MAX_PIE_LABEL_SLICES) {
        const label = { ...firstSeries.label };
        label.show = true;
        label.position = "outside";
        label.formatter = label.formatter ?? "{b} {d}%";
        firstSeries.label = label;
        const labelLine = isRecord(firstSeries.labelLine)
          ? { ...firstSeries.labelLine }
          : {};
        labelLine.show = true;
        firstSeries.labelLine = labelLine;
        firstSeries.avoidLabelOverlap = true;
        delete merged.legend;
      }
    }
    // Keep the LLM's own title (a pie without its subject title looks bare)
    // and shift the ring down slightly so it clears a top title and/or a
    // bottom "数据来源：…" caption instead of overlapping them.
    const hasTitle = isRecord(merged.title)
      ? titleHasText(merged.title)
      : Array.isArray(merged.title)
        ? merged.title.some((item) => isRecord(item) && titleHasText(item))
        : false;
    if (
      (bottomCaption > 0 || hasTitle) &&
      isRecord(firstSeries) &&
      firstSeries.center === undefined
    ) {
      firstSeries.center = ["50%", "49%"];
    }
    // Leave a comfortable gap between the title and the ring: hug a top title
    // to the top edge, cap the outer radius and thin the band so a big thick
    // donut can't crowd the title.
    if (isRecord(merged.title) && !isBottomAnchored(merged.title)) {
      merged.title = { ...merged.title, top: 10 };
    }
    if (isRecord(firstSeries)) {
      normalizePieStyle(firstSeries, bottomCaption > 0 || hasTitle);
    }
  }
  if (primaryType === "funnel") {
    keepBottomCaptions(merged);
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
  if (primaryType === "radar") {
    decorateRadar(merged, palette);
  }
  if (
    usesCartesianAxis &&
    isRecord(merged.title) &&
    isRecord(merged.grid)
  ) {
    const hasSubtext =
      typeof merged.title.subtext === "string" &&
      merged.title.subtext.length > 0;
    const minTop = hasSubtext ? 64 : 48;
    const top = merged.grid.top;
    const numericTop = typeof top === "number" ? top : Number(top);
    if (
      top === undefined ||
      top === "auto" ||
      Number.isNaN(numericTop) ||
      numericTop < minTop
    ) {
      merged.grid.top = minTop;
    }
  }
  // Keep bottom-anchored captions ("数据来源：…") readable below the plot:
  // reserve grid space so the chart and its axis labels sit above the caption
  // instead of overlapping it, and lift any bottom-anchored legend above it.
  // Percent grid bottoms are resolved against the canvas height, which is
  // computed the same way as ChartBlock's container (chartHeight).
  if (usesCartesianAxis && bottomCaption > 0 && isRecord(merged.grid)) {
    const canvasHeight = chartHeight(option);
    const currentBottom = merged.grid.bottom;
    let numericBottom: number | undefined;
    if (typeof currentBottom === "number") {
      numericBottom = currentBottom;
    } else if (typeof currentBottom === "string") {
      const trimmed = currentBottom.trim();
      if (trimmed.endsWith("%")) {
        const percent = Number(trimmed.slice(0, -1));
        numericBottom = Number.isNaN(percent)
          ? undefined
          : (percent / 100) * canvasHeight;
      } else if (trimmed !== "" && trimmed !== "auto") {
        numericBottom = Number(trimmed);
      }
    }
    const reservedBottom = 28 + bottomCaption;
    if (
      numericBottom === undefined ||
      Number.isNaN(numericBottom) ||
      numericBottom < reservedBottom
    ) {
      merged.grid = { ...merged.grid, bottom: reservedBottom };
    }
    if (isRecord(merged.legend)) {
      const legendBottom = merged.legend.bottom;
      const numericLegendBottom =
        typeof legendBottom === "number"
          ? legendBottom
          : Number(legendBottom);
      if (
        legendBottom !== undefined &&
        !Number.isNaN(numericLegendBottom) &&
        numericLegendBottom < bottomCaption + 20
      ) {
        merged.legend = { ...merged.legend, bottom: bottomCaption + 20 };
      }
    }
  }
  sanitizeFormatters(merged);
  normalizeSeriesData(merged);
  decorateSeries(merged, palette);
  return merged as unknown as EChartsOption;
}
