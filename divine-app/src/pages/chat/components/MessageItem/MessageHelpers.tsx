// Pure message/tool helpers: grouping, URL/file extraction, icons, and links.
import type { ReactNode } from "react";
import {
  BarChart3,
  BookMarked,
  ChartBar,
  ChartCandlestick,
  ChartLine,
  ChartNetwork,
  ChartPie,
  ChartScatter,
  Donut,
  FileCode,
  FileSpreadsheet,
  FileStack,
  FileText,
  Funnel,
  Gauge,
  Image,
  Presentation,
  Radar,
} from "lucide-react";
import i18next from "@/i18n";
import { isTauri, openUrl } from "@/services/tauri";
import type { ToolEvent, ToolFileLink } from "@/types";

export function chartOptionFromResult(
  result?: ToolEvent["result"]
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

export const GROUPABLE_TOOLS = new Set([
  "web_search",
  "web_fetch",
  "web_fetch_batch",
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
]);

/**
 * Merge consecutive runs of the same tool into one card while keeping
 * aggregated URLs, files, commands, and a localized summary message.
 */
export function groupToolCards(tools: ToolEvent[]): ToolEvent[] {
  const grouped: ToolEvent[] = [];
  for (const tool of tools) {
    if (!GROUPABLE_TOOLS.has(tool.tool)) {
      grouped.push(tool);
      continue;
    }
    const index = grouped.findIndex((item) => item.tool === tool.tool);
    if (index === -1) {
      const urls = [
        ...new Set([...(tool.urls ?? []), ...toolUrls(tool)]),
      ];
      grouped.push({
        ...tool,
        count: 1,
        urls,
        files: toolFiles(tool),
        commands: toolCommands(tool),
      });
      continue;
    }
    const existing = grouped[index];
    const count = (existing.count ?? 1) + 1;
    const urls = [
      ...new Set([
        ...(existing.urls ?? []),
        ...(tool.urls ?? []),
        ...toolUrls(tool),
      ]),
    ];
    const files = [...new Map(
      [...(existing.files ?? []), ...toolFiles(tool)].map((file) => [
        file.path ?? file.name,
        file,
      ])
    ).values()];
    const commands = [
      ...new Set([
        ...(existing.commands ?? toolCommands(existing)),
        ...toolCommands(tool),
      ]),
    ];
    grouped[index] = {
      ...existing,
      ...tool,
      count,
      urls,
      files,
      commands,
      message:
        tool.tool === "web_search"
          ? i18next.t("tool.completedSearches", "已完成 {{count}} 次搜索", {
              count,
            })
          : tool.tool === "web_fetch" || tool.tool === "web_fetch_batch"
          ? i18next.t("tool.fetchedSources", "已抓取 {{count}} 个数据源", {
              count,
            })
          : tool.tool === "calculator"
            ? i18next.t("tool.completedCalculations", "已完成 {{count}} 次计算", {
                count,
              })
            : tool.tool === "edit_files"
              ? i18next.t("tool.modifiedFiles", "已修改 {{count}} 个文件", {
                  count,
                })
            : tool.tool === "write_file"
              ? i18next.t("tool.writtenFiles", "已写入 {{count}} 个文件", {
                  count,
                })
            : tool.tool === "read_file"
              ? i18next.t("tool.readFiles", "已读取 {{count}} 个文件", {
                  count,
                })
              : tool.tool === "terminal"
                ? i18next.t("tool.executedCommands", "已执行 {{count}} 个终端命令", {
                    count,
                  })
              : tool.tool === "grep_files"
                ? i18next.t("tool.grepSearches", "已完成 {{count}} 次内容搜索", {
                    count,
                  })
              : i18next.t("tool.executedTimes", "{{tool}} 已执行 {{count}} 次", {
                  tool: tool.tool.toUpperCase(),
                  count,
                }),
    };
  }
  return grouped;
}

export function toolUrls(tool: ToolEvent): string[] {
  const urls: string[] = [];
  const data = tool.result?.data;
  if (Array.isArray(data?.results)) {
    for (const item of data.results) {
      if (
        item &&
        typeof item === "object" &&
        "url" in item &&
        typeof item.url === "string"
      ) {
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
      if (
        item &&
        typeof item === "object" &&
        "path" in item &&
        typeof item.path === "string"
      ) {
        const rawName = item.path.split("/").pop() ?? item.path;
        files.push({
          name:
            item.action === "created"
              ? i18next.t("tool.addedFile", "新增 {{name}}", { name: rawName })
              : i18next.t("tool.modifiedFile", "修改 {{name}}", { name: rawName }),
          path:
            "filepath" in item && typeof item.filepath === "string"
              ? item.filepath
              : item.path,
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
            : item.filepath.split("/").pop() ?? item.filepath;
        files.push({
          name: rawName,
          path: item.filepath,
          download_url:
            "download_url" in item && typeof item.download_url === "string"
              ? item.download_url
              : undefined,
          size:
            "file_size" in item && typeof item.file_size === "number"
              ? item.file_size
              : undefined,
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

export function fileIcon(file: ToolFileLink): ReactNode {
  const source = file.path || file.name || "";
  const ext = source.includes(".")
    ? source.split(".").pop()?.toLowerCase() ?? ""
    : "";
  if (
    [
      "rs",
      "py",
      "ts",
      "tsx",
      "js",
      "jsx",
      "go",
      "java",
      "c",
      "h",
      "cpp",
      "rb",
      "sh",
      "toml",
      "yaml",
      "yml",
      "json",
      "css",
      "scss",
      "html",
      "vue",
      "svelte",
    ].includes(ext)
  ) {
    return <FileCode size={14} />;
  }
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "ico"].includes(ext)) {
    return <Image size={14} />;
  }
  if (["xlsx", "xls", "csv", "numbers"].includes(ext)) {
    return <FileSpreadsheet size={14} />;
  }
  if (["pptx", "ppt", "key"].includes(ext)) {
    return <Presentation size={14} />;
  }
  if (["docx", "doc", "pages"].includes(ext)) {
    return <BookMarked size={14} />;
  }
  if (["pdf"].includes(ext)) {
    return <FileStack size={14} />;
  }
  if (["md", "markdown", "txt", "rst"].includes(ext)) {
    return <FileText size={14} />;
  }
  return <FileText size={14} />;
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
  const first =
    series.find((item) => isChartSeries(item)) ??
    ({} as Record<string, unknown>);
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
  value: unknown
): value is Record<string, unknown> & { type?: unknown } {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    "type" in value
  );
}
