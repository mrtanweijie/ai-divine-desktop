// Renders a single tool status card, including approvals and file actions.
import { memo, useCallback, useState } from "react";
import { AlertCircle, CalendarClock, Check, ChevronDown, Copy, Link } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import { ChartBlock } from "@/pages/chat/components/ChartBlock";
import { GraphBlock } from "@/pages/chat/components/GraphBlock";
import { request } from "@/services/request";
import type { PreviewFile, ToolEvent } from "@/types";
import { copyText } from "@/utils";
import {
  chartOptionFromResult,
  chartTypeIcon,
  graphIRFromResult,
  openToolUrl,
} from "./MessageHelpers";
import { ToolCommands } from "./ToolCommands";
import { ToolConfirmSection } from "./ToolConfirmSection";
import { ToolFileList, ToolResultFile } from "./ToolFileList";
import { toolIcon } from "./ToolStatusIcon";
import { DiffView } from "./DiffView";

export const ToolStatusCard = memo(function ToolStatusCard({
  tool,
  sessionId,
  workspacePath,
  live = false,
  onPreviewFile,
}: {
  tool: ToolEvent;
  sessionId?: string | null;
  workspacePath?: string | null;
  /** 该消息仍在流式输出 = 本轮新生成的图，播放回放式入场；
   *  历史消息直渲染终态（零动画、不自动开流动）。 */
  live?: boolean;
  onPreviewFile?: (file: PreviewFile) => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [decideError, setDecideError] = useState<string | null>(null);
  const [commandsOpen, setCommandsOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const [urlsOpen, setUrlsOpen] = useState(false);
  const targetSessionId = tool.session_id ?? sessionId;
  const running = tool.status === "running" || tool.status === "preparing";
  const urls = tool.urls ?? [];
  const hasUrls = urls.length > 0;
  const toggleUrls = useCallback(() => setUrlsOpen((value) => !value), []);
  // 这三类工具的文件列表默认收起，点击卡片头部展开（read_file 原有行为；
  // write_file / edit_files 批量写文件时列表过长，同样收起）。
  // generate_chart 合并卡（SVG 图表 ≥2 个）同样默认收起，点击展开。
  const collapsibleFiles =
    tool.tool === "read_file" ||
    tool.tool === "write_file" ||
    tool.tool === "edit_files" ||
    (tool.tool === "generate_chart" && (tool.files?.length ?? 0) > 1);
  const hasFiles = collapsibleFiles && (tool.files?.length ?? 0) > 0;
  const toggleFiles = useCallback(() => setFilesOpen((value) => !value), []);
  const statusMessage =
    tool.status === "running" && tool.currentUrl
      ? t("tool.fetchingUrl", "正在抓取：{{url}}", {
          url: tool.currentUrl,
        })
      : tool.count && tool.count > 1
        ? tool.message
        : tool.status === "done"
          ? t("tool.done", "执行完成")
          : tool.messageKey
            ? t(tool.messageKey, tool.messageParams ?? {})
            : tool.message;
  const chartOption = chartOptionFromResult(tool.result);
  const chartIcon = chartOption ? chartTypeIcon(chartOption) : null;
  const graphIR = graphIRFromResult(tool.result);
  const icon = toolIcon(tool.tool);

  const copyJson = async () => {
    if (!tool.result) return;
    await copyText(JSON.stringify(tool.result, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  const decide = async (allow: boolean) => {
    if (!targetSessionId || deciding) return;
    setDeciding(true);
    setDecideError(null);
    try {
      const result = await request<{ ok?: boolean; message?: string }>("/terminal/decide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: targetSessionId, allow }),
      });
      if (result && result.ok === false) {
        setDecideError(result.message || t("tool.decideFailed", "确认失败，请重试"));
      }
    } catch (error) {
      setDecideError(
        error instanceof Error ? error.message : t("tool.decideFailed", "确认失败，请重试"),
      );
    } finally {
      setDeciding(false);
    }
  };

  return (
    <div className={`tool-status-card ${tool.status}`}>
      <Flex
        align="center"
        gap={8}
        className={`tool-status-main${hasUrls || hasFiles ? " clickable" : ""}`}
        onClick={hasUrls ? toggleUrls : hasFiles ? toggleFiles : undefined}
        role={hasUrls || hasFiles ? "button" : undefined}
        tabIndex={hasUrls || hasFiles ? 0 : undefined}
        aria-expanded={hasUrls ? urlsOpen : hasFiles ? filesOpen : undefined}
        onKeyDown={
          hasUrls || hasFiles
            ? (event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  if (hasUrls) toggleUrls();
                  else if (hasFiles) toggleFiles();
                }
              }
            : undefined
        }
      >
        <span className="tool-icon">
          {running ? <LoadingOrb state="solving" size={20} speed={3} /> : icon}
        </span>
        <div className="tool-copy">
          <span className="tool-name">
            {tool.tool === "preprocess_fallback"
              ? t("tool.preprocessFallbackTitle", "本地整理失败")
              : tool.tool === "ask_user"
                ? t("tool.askUserTitle", "向用户提问")
                : tool.tool}
          </span>
          <span
            className={`tool-message${
              tool.status === "running" && tool.currentUrl ? " nowrap" : ""
            }`}
          >
            {statusMessage}
          </span>
        </div>
        {(typeof tool.turn === "number" && tool.turn > 0) ||
        tool.duration_ms != null ||
        (tool.failed_count ?? 0) > 0 ? (
          <span className="tool-meta">
            {typeof tool.turn === "number" && tool.turn > 0
              ? (() => {
                  const start = tool.turn_start ?? tool.turn;
                  return start != null && start !== tool.turn
                    ? t("tool.turnRangeBadge", "第 {{start}}–{{end}} 轮", {
                        start,
                        end: tool.turn,
                      })
                    : t("tool.turnBadge", "第 {{turn}} 轮", { turn: tool.turn });
                })()
              : ""}
            {tool.duration_ms != null
              ? `${tool.turn != null && tool.turn > 0 ? " · " : ""}${
                  tool.duration_ms < 1000
                    ? `${tool.duration_ms}ms`
                    : `${(tool.duration_ms / 1000).toFixed(1)}s`
                }`
              : ""}
            {(tool.failed_count ?? 0) > 0
              ? ` · ${t("tool.failedBadge", "失败 ×{{count}}", {
                  count: tool.failed_count,
                })}`
              : ""}
          </span>
        ) : null}
        {hasUrls && (
          <>
            <span className="tool-url-count">
              {t("tool.urlCount", "{{count}} 个链接", {
                count: urls.length,
              })}
            </span>
            <ChevronDown size={14} className={`tool-url-chevron${urlsOpen ? " expanded" : ""}`} />
          </>
        )}
        {hasFiles && (
          <>
            <span className="tool-url-count">
              {t("tool.fileCount", "{{count}} 个文件", {
                count: tool.files?.length ?? 0,
              })}
            </span>
            <ChevronDown size={14} className={`tool-url-chevron${filesOpen ? " expanded" : ""}`} />
          </>
        )}
      </Flex>
      {tool.status === "done" && chartOption && (
        <div className="chart-block">
          <ChartBlock option={chartOption} workspacePath={workspacePath} />
        </div>
      )}
      {tool.status === "done" && graphIR && (
        <GraphBlock ir={graphIR} workspacePath={workspacePath} animate={live} />
      )}
      {hasUrls && urlsOpen && (
        <div className="tool-url-list">
          {urls.map((url) => (
            <div
              key={url}
              role="link"
              tabIndex={0}
              className="tool-url-link"
              onClick={() => void openToolUrl(url)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  void openToolUrl(url);
                }
              }}
              title={url}
            >
              <Link size={13} />
              <span>{url}</span>
            </div>
          ))}
        </div>
      )}
      {tool.files && tool.files.length > 0 && (!collapsibleFiles || filesOpen) && (
        <ToolFileList
          tool={tool}
          workspacePath={workspacePath}
          onPreviewFile={onPreviewFile}
          filesOpen={filesOpen}
          onToggleFiles={toggleFiles}
        />
      )}
      {tool.tool === "edit_files" &&
        tool.status === "done" &&
        typeof tool.result?.data?.diff === "string" &&
        tool.result.data.diff.trim().length > 0 && <DiffView diff={tool.result.data.diff} />}
      <ToolResultFile tool={tool} workspacePath={workspacePath} onPreviewFile={onPreviewFile} />
      <ToolCommands
        tool={tool}
        commandsOpen={commandsOpen}
        onToggleCommands={() => setCommandsOpen(true)}
      />
      <ToolConfirmSection
        tool={tool}
        deciding={deciding}
        targetSessionId={targetSessionId}
        onDecide={(allow) => void decide(allow)}
      />
      {tool.status === "confirm" && decideError && (
        <div className="message-error">
          <AlertCircle size={13} />
          <span>{decideError}</span>
        </div>
      )}
      {tool.status === "done" &&
        tool.result &&
        tool.tool !== "web_fetch" &&
        tool.tool !== "web_fetch_batch" && (
          <Flex align="center" gap={8} className="tool-result-actions">
            {chartIcon ?? icon}
            <span>
              {tool.result.messageKey
                ? t(tool.result.messageKey, tool.result.messageParams ?? {})
                : (tool.result.message ?? "")}
            </span>
            {tool.tool !== "schedule_task" && (
              <Button
                variant="icon"
                size="small"
                onClick={copyJson}
                title={t("tool.copyResult", "复制结果")}
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
              </Button>
            )}
            {tool.tool === "schedule_task" && (
              <Button
                size="small"
                className="manage-tasks-button"
                onClick={() => window.dispatchEvent(new CustomEvent("divine:open-tasks"))}
                title={t("tool.manageTasks", "管理定时任务")}
              >
                <CalendarClock size={13} />
                {t("tool.manageTasks", "管理任务")}
              </Button>
            )}
          </Flex>
        )}
    </div>
  );
});
