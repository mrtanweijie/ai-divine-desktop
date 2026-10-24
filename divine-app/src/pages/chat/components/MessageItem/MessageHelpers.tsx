// Pure message/tool helpers: grouping, URL/file extraction, icons, and links.
import type { ReactNode } from "react";
import {
  BarChart3,
  ChartBar,
  ChartCandlestick,
  ChartLine,
  ChartNetwork,
  ChartPie,
  ChartScatter,
  Donut,
  Funnel,
  Gauge,
  Radar,
} from "lucide-react";
import i18next from "@/i18n";
import { type GraphIR, parseGraphIR } from "@/pages/chat/components/GraphBlock/GraphIR";
import { isTauri, openUrl } from "@/services/tauri";
import type { ToolEvent, ToolFileLink } from "@/types";

export function chartOptionFromResult(
  result?: ToolEvent["result"],
): Record<string, unknown> | null {
  const data = result?.data;
  // export_svg=true 时只显示 SVG 文件，不渲染内联图表
  if (data && data.export_svg === true) {
    return null;
  }
  if (data && data.option && typeof data.option === "object") {
    return data.option as Record<string, unknown>;
  }
  if (result?.option && typeof result.option === "object") {
    return result.option as Record<string, unknown>;
  }
  return null;
}

/**
 * render_graph 的 GraphIR：与 chartOptionFromResult 同一个提取层。
 * 校验（白名单 / 枚举 / 引用完整性）在 GraphBlock/GraphIR.ts 里做——
 * IR 来自 LLM 且会从持久化结果里二次读取，一律按不可信输入处理。
 */
export function graphIRFromResult(result?: ToolEvent["result"]): GraphIR | null {
  const raw = result?.data?.graphIR;
  if (!raw) return null;
  const parsed = parseGraphIR(raw);
  if (!parsed.ok) {
    console.warn("[GraphBlock] 拒绝渲染非法 GraphIR:", parsed.reason);
    return null;
  }
  return parsed.ir;
}

/**
 * 工具卡状态行的**单行化**：卡片是状态位，不是报错控制台。
 *
 * `tool.message` 可能是多行长文本（典型：`render_ui` 校验失败时把十几条
 * 路径级错误全铺出来，`ux_html`/`html_generate` 的静态校验警告同理）。
 * 这类文本是**给模型自纠用的**，用户只需要知道"失败了、为什么败"。
 *
 * 规则：取**第一个非空行**（后端 summary 首行就是 `xxx 校验未通过（13 处）：`
 * 这种可读摘要，且原文常以 `\n` 开头），后面还有内容则在末尾补 `…`——补之前
 * 去掉摘要行末尾的冒号，避免出现 `（13 处）：…` 这种叠在一起的标点；
 * 完整文本由调用方挂 `title` 悬停查看。**只影响展示，不改回灌模型的内容。**
 */
export function toolMessageLine(message: string): { text: string; more: boolean } {
  const lines = message.split("\n").map((line) => line.trim());
  const firstIndex = lines.findIndex((line) => line.length > 0);
  if (firstIndex === -1) return { text: "", more: false };
  const rest = lines.slice(firstIndex + 1).some((line) => line.length > 0);
  const text = rest ? lines[firstIndex].replace(/[：:]\s*$/, "") : lines[firstIndex];
  return { text, more: rest };
}

export const GROUPABLE_TOOLS = new Set([
  "web_search",
  "web_fetch",
  "web_fetch_batch",
  "web_task",
  "svg_to_png",
  "svg_to_png_batch",
  "mermaid_export",
  "notes",
  "word_document",
  "presentation",
  "spreadsheet",
  "draw_svg",
  "edit_svg",
  "pdf_split_merge",
  "clipboard",
  "image_resize",
  "calculator",
  "sqlite_query",
  "rag_search",
  "read_file",
  "edit_files",
  "edit_lines",
  "apply_patch",
  "document_outline",
  "pdf_form_fields",
  "pdf_form_fill",
  "pdf_to_word",
  "fill_template",
  "edit_docx",
  "edit_xlsx",
  "edit_pptx",
  "move_file",
  "write_file",
  "search_files",
  "grep_files",
  "directory_tree",
  "glob_files",
  "terminal",
  "lint_check",
  "run_tests",
  "format_code",
  "git_status",
  "git_diff",
  "git_log",
  "git_commit",
  "git_revert",
  "bg_status",
  "bg_output",
  "bg_kill",
  "list_definitions",
  "remember",
  "forget_memory",
]);

/**
 * generate_chart 的 SVG 导出运行（export_svg=true）可合并：这类调用不渲染
 * 内联图表（chartOptionFromResult 返回 null），只落一个 SVG 文件，连排多次
 * 逐条成卡是纯刷屏。内联图表运行（export_svg=false/缺省，含尚未出结果的
 * running 态）绝不进组——避免「多张图表只显示最后一张」的回归。
 */
function isSvgChartRun(tool: ToolEvent): boolean {
  return tool.tool === "generate_chart" && tool.result?.data?.export_svg === true;
}

/** Office 读取/编辑工具合并卡片上的聚合计数文案 key。 */
const OFFICE_COUNT_KEYS: Record<string, string> = {
  document_outline: "tool.outlinedDocuments",
  pdf_form_fields: "tool.formFieldsListed",
  pdf_form_fill: "tool.formsFilled",
  pdf_to_word: "tool.convertedPdfs",
  fill_template: "tool.filledTemplates",
  edit_docx: "tool.editedWordDocs",
  edit_xlsx: "tool.editedExcelSheets",
  edit_pptx: "tool.editedPptDecks",
};

/** 合并卡片的聚合计数文案（Office 工具走专用 key，其余按工具族归类）。 */
function mergedCountMessage(tool: ToolEvent, count: number): string {
  const officeKey = OFFICE_COUNT_KEYS[tool.tool];
  if (officeKey) {
    return i18next.t(officeKey, "{{tool}} 已执行 {{count}} 次", { count });
  }
  if (tool.tool === "web_search") {
    return i18next.t("tool.completedSearches", "已完成 {{count}} 次搜索", { count });
  }
  if (tool.tool === "generate_chart") {
    // 只合并 SVG 导出运行（isSvgChartRun 把关）
    return i18next.t("tool.generatedSvgCharts", "已生成 {{count}} 个 SVG 图表", { count });
  }
  if (tool.tool === "web_fetch" || tool.tool === "web_fetch_batch") {
    return i18next.t("tool.fetchedSources", "已抓取 {{count}} 个数据源", { count });
  }
  if (tool.tool === "web_task") {
    // 多段委派合并：状态行只显示段数；失败保留末段错误文本
    return tool.status === "error"
      ? tool.message
      : i18next.t("tool.completedWebTasks", "已完成 {{count}} 段委派", { count });
  }
  if (tool.tool === "calculator") {
    return i18next.t("tool.completedCalculations", "已完成 {{count}} 次计算", { count });
  }
  if (tool.tool === "edit_files") {
    return i18next.t("tool.modifiedFiles", "已修改 {{count}} 个文件", { count });
  }
  if (tool.tool === "write_file") {
    return i18next.t("tool.writtenFiles", "已写入 {{count}} 个文件", { count });
  }
  if (tool.tool === "read_file") {
    return i18next.t("tool.readFiles", "已读取 {{count}} 个文件", { count });
  }
  if (tool.tool === "terminal") {
    return i18next.t("tool.executedCommands", "已执行 {{count}} 个终端命令", { count });
  }
  if (tool.tool === "grep_files") {
    return i18next.t("tool.grepSearches", "已完成 {{count}} 次内容搜索", { count });
  }
  if (tool.tool.startsWith("git_")) {
    return i18next.t("tool.gitOperations", "已完成 {{count}} 次 Git 操作", { count });
  }
  if (tool.tool.startsWith("bg_")) {
    return i18next.t("tool.bgOperations", "已执行 {{count}} 次后台操作", { count });
  }
  if (tool.tool === "list_definitions") {
    return i18next.t("tool.listedDefinitions", "已查看 {{count}} 个文件大纲", { count });
  }
  if (tool.tool === "remember" || tool.tool === "forget_memory") {
    return i18next.t("tool.memoryOperations", "已完成 {{count}} 次记忆操作", { count });
  }
  return i18next.t("tool.executedTimes", "{{tool}} 已执行 {{count}} 次", {
    tool: tool.tool.toUpperCase(),
    count,
  });
}

/**
 * Merge consecutive runs of the same tool into one card while keeping
 * aggregated URLs, files, commands, and a localized summary message.
 *
 * 两条合并规则：
 * 1. 白名单工具（GROUPABLE_TOOLS）：跨位置全局合并，聚合消息。
 * 2. 失败重试链（所有工具）：相邻同工具且链上出现过失败即合并——
 *    连续重试失败刷屏是明确的体验伤害；纯成功链不合，
 *    多次成功调用可能有各自结果（如多张图表），不应吞掉。
 */
export function groupToolCards(tools: ToolEvent[]): ToolEvent[] {
  const grouped: ToolEvent[] = [];
  for (const tool of tools) {
    // 白名单工具 + generate_chart 的 SVG 导出运行走全局合并
    const groupable = GROUPABLE_TOOLS.has(tool.tool) || isSvgChartRun(tool);
    if (!groupable) {
      const last = grouped[grouped.length - 1];
      // 仅当上一张卡以失败收尾时才续链：error→error 续链、error→done 收链。
      // 成功卡永远开新卡——多次成功调用可能有各自结果（如多张图表），
      // 不能被之前的重试历史永久吸附（已踩坑：多图表只显示最后一张）。
      if (last && last.tool === tool.tool && last.status === "error") {
        grouped[grouped.length - 1] = mergeRetryChain(last, tool);
        continue;
      }
      grouped.push(tool);
      continue;
    }
    const index = grouped.findIndex((item) => item.tool === tool.tool);
    if (index === -1) {
      const urls = [...new Set([...(tool.urls ?? []), ...toolUrls(tool)])];
      grouped.push({
        ...tool,
        count: 1,
        turn_start: tool.turn,
        failed_count: tool.status === "error" ? 1 : 0,
        urls,
        files: toolFiles(tool),
        commands: toolCommands(tool),
      });
      continue;
    }
    const existing = grouped[index];
    const count = (existing.count ?? 1) + 1;
    const failed =
      (existing.failed_count ?? (existing.status === "error" ? 1 : 0)) +
      (tool.status === "error" ? 1 : 0);
    const urls = [...new Set([...(existing.urls ?? []), ...(tool.urls ?? []), ...toolUrls(tool)])];
    const files = [
      ...new Map(
        [...(existing.files ?? []), ...toolFiles(tool)].map((file) => [
          file.path ?? file.name,
          file,
        ]),
      ).values(),
    ];
    const commands = [
      ...new Set([...(existing.commands ?? toolCommands(existing)), ...toolCommands(tool)]),
    ];
    grouped[index] = {
      ...existing,
      ...tool,
      result: tool.result ?? existing.result,
      count,
      failed_count: failed,
      turn_start: existing.turn_start ?? existing.turn,
      urls,
      files,
      commands,
      message: mergedCountMessage(tool, count),
    };
  }
  return grouped;
}

/**
 * 失败重试链合并：保留最终结果的 result（重试成功后图表/文件正常展示），
 * 消息区分「重试后成功」与「仍在失败」两种终态。
 */
function mergeRetryChain(existing: ToolEvent, tool: ToolEvent): ToolEvent {
  const count = (existing.count ?? 1) + 1;
  const failed =
    (existing.failed_count ?? (existing.status === "error" ? 1 : 0)) +
    (tool.status === "error" ? 1 : 0);
  const succeeded = tool.status !== "error" && failed > 0;
  return {
    ...existing,
    ...tool,
    result: tool.result ?? existing.result,
    count,
    failed_count: failed,
    turn_start: existing.turn_start ?? existing.turn,
    message: succeeded
      ? i18next.t("tool.retriedSuccess", "重试 {{count}} 次后成功", {
          count: failed,
        })
      : tool.message,
  };
}

export function toolUrls(tool: ToolEvent): string[] {
  const urls: string[] = [];
  const data = tool.result?.data;
  if (Array.isArray(data?.results)) {
    for (const item of data.results) {
      if (item && typeof item === "object" && "url" in item && typeof item.url === "string") {
        urls.push(item.url);
      }
    }
  }
  if (data && typeof data.url === "string") {
    urls.push(data.url);
  }
  const message = tool.result?.message ?? tool.message ?? "";
  const matches = message.match(/https?:\/\/[^\s，。、,;；]+/g);
  if (matches) {
    urls.push(...matches);
  }
  return [...new Set(urls)];
}

/** Extract file links from a tool result, including edit_files/results arrays. */
export function toolFiles(tool: ToolEvent): ToolFileLink[] {
  const files: ToolFileLink[] = [];
  const data = tool.result?.data;
  if (Array.isArray(data?.files)) {
    for (const item of data.files) {
      if (item && typeof item === "object" && "path" in item && typeof item.path === "string") {
        const rawName = item.path.split("/").pop() ?? item.path;
        files.push({
          name:
            item.action === "created"
              ? i18next.t("tool.addedFile", "新增 {{name}}", { name: rawName })
              : i18next.t("tool.modifiedFile", "修改 {{name}}", { name: rawName }),
          path: "filepath" in item && typeof item.filepath === "string" ? item.filepath : item.path,
          download_url: undefined,
          size: undefined,
        });
      }
    }
  }
  if (Array.isArray(data?.results)) {
    for (const item of data.results) {
      if (
        item &&
        typeof item === "object" &&
        "filepath" in item &&
        typeof item.filepath === "string"
      ) {
        const rawName =
          "file_name" in item && typeof item.file_name === "string"
            ? item.file_name
            : (item.filepath.split("/").pop() ?? item.filepath);
        files.push({
          name: rawName,
          path: item.filepath,
          download_url:
            "download_url" in item && typeof item.download_url === "string"
              ? item.download_url
              : undefined,
          size:
            "file_size" in item && typeof item.file_size === "number" ? item.file_size : undefined,
        });
      }
    }
  }
  if (tool.result?.filepath) {
    files.push({
      name: tool.result.file_name ?? tool.result.filepath.split("/").pop() ?? "file",
      path: tool.result.filepath,
      download_url: tool.result.download_url,
      size: tool.result.file_size,
    });
  }
  return files;
}

export function toolCommands(tool: ToolEvent): string[] {
  if (tool.commands?.length) return tool.commands;
  return tool.command ? [tool.command] : [];
}

export async function openToolUrl(url: string): Promise<void> {
  if (isTauri()) {
    await openUrl(url);
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

/** Pick a lucide chart icon based on the primary ECharts series type. */
export function chartTypeIcon(option: Record<string, unknown>): ReactNode {
  const series = Array.isArray(option.series) ? option.series : [];
  const first = series.find((item) => isChartSeries(item)) ?? ({} as Record<string, unknown>);
  const type = typeof first.type === "string" ? first.type : "";
  switch (type) {
    case "line":
    case "lines":
      return <ChartLine size={13} />;
    case "bar":
    case "pictorialBar":
    case "heatmap":
      return <ChartBar size={13} />;
    case "pie": {
      const radius = first.radius;
      return Array.isArray(radius) && radius.length > 1 ? (
        <Donut size={13} />
      ) : (
        <ChartPie size={13} />
      );
    }
    case "scatter":
    case "effectScatter":
      return <ChartScatter size={13} />;
    case "radar":
      return <Radar size={13} />;
    case "funnel":
      return <Funnel size={13} />;
    case "gauge":
      return <Gauge size={13} />;
    case "candlestick":
    case "boxplot":
      return <ChartCandlestick size={13} />;
    case "sankey":
    case "graph":
    case "tree":
      return <ChartNetwork size={13} />;
    case "sunburst":
    case "treemap":
      return <ChartPie size={13} />;
    default:
      return <BarChart3 size={13} />;
  }
}

export function isChartSeries(
  value: unknown,
): value is Record<string, unknown> & { type?: unknown } {
  return typeof value === "object" && value !== null && !Array.isArray(value) && "type" in value;
}
