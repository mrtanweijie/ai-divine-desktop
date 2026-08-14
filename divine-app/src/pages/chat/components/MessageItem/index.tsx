import {
  AlertCircle,
  BarChart3,
  BookAudio,
  BookMarked,
  BookSearch,
  Calculator,
  CalendarClock,
  CalendarDays,
  ChartBar,
  ChartCandlestick,
  ChartLine,
  ChartNetwork,
  ChartPie,
  ChartScatter,
  Check,
  ChevronDown,
  Copy,
  Database,
  Donut,
  Eye,
  FileBox,
  FileStack,
  FileCode,
  FileCode2,
  FileSpreadsheet,
  FileText,
  FolderSearch2,
  FolderOpen,
  FolderTree,
  Funnel,
  Gauge,
  Group,
  Globe,
  Image,
  ImageDown,
  LibraryBig,
  ListChecks,
  Link,
  Orbit,
  PenTool,
  Presentation,
  Radar,
  SquareKanban,
  StickyNote,
  TerminalSquare,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import i18next from "@/i18n";
import { downloadUrl } from "@/services/api";
import { isTauri, openFileLocation, openUrl } from "@/services/tauri";
import { request } from "@/services/request";
import type {
  ChatMessage,
  PreviewFile,
  TodoItem,
  ToolEvent,
  ToolFileLink,
} from "@/types";
import { formatSize, formatTime } from "@/utils";
import { toWorkspaceRelative } from "@/services/workspace";
import { MarkdownView } from "@/pages/chat/components/MarkdownView";
import { ChartBlock } from "@/pages/chat/components/ChartBlock";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import { DivineAvatar } from "@/components/DivineAvatar";

interface MessageItemProps {
  message: ChatMessage;
  streaming: boolean;
  sessionId?: string | null;
  username: string;
  workspacePath?: string | null;
  onPreviewFile?: (file: PreviewFile) => void;
  onUserInteract?: () => void;
}

export function MessageItem({
  message,
  streaming,
  sessionId,
  username,
  workspacePath,
  onPreviewFile,
  onUserInteract,
}: MessageItemProps) {
  const { t } = useTranslation();
  const isUser = message.role === "user";
  return (
    <article className={`message-row ${isUser ? "user-message" : "assistant-message"}`}>
      <Flex
        align="center"
        justify={isUser ? "end" : "start"}
        gap={8}
        className="message-meta"
      >
        {!isUser && (
          <DivineAvatar />
        )}
        <span className="role-label">
          {isUser ? username || t("common.user", "用户") : "Divine"}
        </span>
        <time className="message-time">{formatTime(message.created_at)}</time>
      </Flex>
      {isUser ? (
        <div className="user-content">
          <div className="user-text">{message.content}</div>
          {message.files && message.files.length > 0 && (
            <div className="user-files">
              {message.files.map((file) => (
                <div
                  className={`user-file-card${
                    file.path || file.content ? " previewable" : ""
                  }`}
                  key={file.name}
                  role={file.path || file.content ? "button" : undefined}
                  tabIndex={file.path || file.content ? 0 : undefined}
                  onClick={
                    file.path || file.content
                      ? () =>
                          onPreviewFile?.({
                            repoPath: "",
                            relPath: file.name,
                            fileName: file.name,
                            path: file.path,
                            content: file.content,
                          })
                      : undefined
                  }
                  onKeyDown={
                    file.path || file.content
                      ? (event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            onPreviewFile?.({
                              repoPath: "",
                              relPath: file.name,
                              fileName: file.name,
                              path: file.path,
                              content: file.content,
                            });
                          }
                        }
                      : undefined
                  }
                >
                  <FileText size={13} />
                  <span>{file.name}</span>
                  {file.size != null && (
                    <span className="user-file-size">
                      {formatSize(file.size)}
                    </span>
                  )}
                  {(file.path || file.content) && <Eye size={13} />}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="assistant-content">
          {message.think && (
            <ThinkBlock
              content={message.think}
              onUserInteract={onUserInteract}
            />
          )}
          {message.todos && message.todos.length > 0 && (
            <PlanCard todos={message.todos} />
          )}
          {groupToolCards(message.tools).map((tool, index) => (
            <ToolStatusCard
              key={`${tool.tool}-${index}`}
              tool={tool}
              sessionId={sessionId}
              workspacePath={workspacePath}
              onPreviewFile={onPreviewFile}
            />
          ))}
          {message.content ? (
            <MarkdownView content={message.content} streaming={streaming} />
          ) : (
            !message.error && (
              <Flex
                className="loading-cursor"
                aria-label={t("message.generating", "正在生成")}
              >
                <LoadingOrb state="shaping" size={20} speed={2} />
              </Flex>
            )
          )}
          {streaming && message.content && (
            <span className="stream-orb">
              <LoadingOrb state="connecting" size={20} speed={2} />
              <span className="stream-text">
                {t("message.working", "Working...")}
              </span>
            </span>
          )}
          {message.error && (
            <div className="message-error">
              <AlertCircle size={15} />
              <span>{message.error}</span>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function ThinkBlock({
  content,
  onUserInteract,
}: {
  content: string;
  onUserInteract?: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const blockRef = useRef<HTMLDetailsElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  useEffect(() => {
    const content = contentRef.current;
    if (open && content && stickToBottom.current) {
      content.scrollTop = content.scrollHeight;
    }
  }, [content, open]);
  const handleContentScroll = () => {
    const content = contentRef.current;
    if (!content) return;
    const distance =
      content.scrollHeight - content.scrollTop - content.clientHeight;
    stickToBottom.current = distance < 24;
  };
  const toggle = () => {
    const container = blockRef.current?.closest<HTMLElement>(
      ".message-timeline"
    );
    const scrollTop = container?.scrollTop ?? 0;
    onUserInteract?.();
    setOpen((value) => !value);
    requestAnimationFrame(() => {
      if (container) container.scrollTop = scrollTop;
    });
    requestAnimationFrame(() => {
      if (container) container.scrollTop = scrollTop;
    });
  };
  return (
    <details className="think-block" open={open} ref={blockRef}>
      <summary
        className="think-summary"
        onClick={(event) => {
          event.preventDefault();
          toggle();
        }}
      >
        <ChevronDown size={13} className={open ? "expanded" : ""} />
        <span>{t("message.thinking", "思考过程")}</span>
      </summary>
      <div
        className="think-content"
        ref={contentRef}
        onScroll={handleContentScroll}
      >
        {content}
      </div>
    </details>
  );
}

function PlanCard({ todos }: { todos: TodoItem[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);
  const done = todos.filter((todo) => todo.status === "done").length;
  return (
    <details className="plan-block" open={open}>
      <summary
        className="plan-summary"
        onClick={(event) => {
          event.preventDefault();
          setOpen((value) => !value);
        }}
      >
        <ChevronDown size={13} className={open ? "expanded" : ""} />
        <span>{t("message.plan", "执行计划")}</span>
        <span className="plan-progress">
          {done}/{todos.length}
        </span>
      </summary>
      <div className="plan-items">
        {todos.map((todo, index) => (
          <div
            key={todo.id || `plan-${index}`}
            className={`plan-item ${todo.status}`}
          >
            <span className="plan-item-icon">
              {todo.status === "done" ? (
                <Check size={13} />
              ) : todo.status === "error" ? (
                <AlertCircle size={13} />
              ) : todo.status === "running" ? (
                <span className="plan-spinner" />
              ) : (
                <span className="plan-dot" />
              )}
            </span>
            <span className="plan-item-title">{todo.title}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

function ToolStatusCard({
  tool,
  sessionId,
  workspacePath,
  onPreviewFile,
}: {
  tool: ToolEvent;
  sessionId?: string | null;
  workspacePath?: string | null;
  onPreviewFile?: (file: PreviewFile) => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [decideError, setDecideError] = useState<string | null>(null);
  const [commandsOpen, setCommandsOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const targetSessionId = tool.session_id ?? sessionId;
  const running = tool.status === "running" || tool.status === "preparing";
  const statusMessage =
    tool.count && tool.count > 1
      ? tool.message
      : tool.status === "done"
        ? t("tool.done", "执行完成")
        : tool.messageKey
          ? t(tool.messageKey, tool.messageParams ?? {})
          : tool.message;
  const chartOption = chartOptionFromResult(tool.result);
  const chartIcon = chartOption ? chartTypeIcon(chartOption) : null;
  const workspaceRel = useMemo(
    () =>
      workspacePath && tool.result?.filepath
        ? toWorkspaceRelative(workspacePath, tool.result.filepath)
        : null,
    [tool.result?.filepath, workspacePath]
  );
  const icon =
    tool.tool === "edit_files" ? (
      <Group size={16} />
    ) : tool.tool === "draw_svg" ? (
      <FileBox size={16} />
    ) : tool.tool === "describe_svg" || tool.tool === "edit_svg" ? (
      <Orbit size={16} />
    ) : tool.tool.includes("svg_to_png") ? (
      <ImageDown size={16} />
    ) : tool.tool.includes("svg") ? (
      <PenTool size={16} />
    ) : tool.tool === "schedule_task" ? (
      <CalendarClock size={16} />
    ) : tool.tool === "write_calendar" ? (
      <CalendarDays size={16} />
    ) : tool.tool.includes("spreadsheet") || tool.tool.includes("excel") ? (
      <FileSpreadsheet size={16} />
    ) : tool.tool.includes("notes") ? (
      <StickyNote size={16} />
    ) : tool.tool === "read_file" ? (
      <BookMarked size={16} />
    ) : tool.tool.includes("read_image") || tool.tool.includes("image") ? (
      <Image size={16} />
    ) : tool.tool.includes("calculator") ? (
      <Calculator size={16} />
    ) : tool.tool.includes("clipboard") ? (
      <Copy size={16} />
    ) : tool.tool.includes("sqlite") || tool.tool.includes("database") ? (
      <Database size={16} />
    ) : tool.tool.includes("rag_index") ? (
      <LibraryBig size={16} />
    ) : tool.tool.includes("rag_search") ? (
      <BookSearch size={16} />
    ) : tool.tool.includes("search_files") ||
      tool.tool.includes("search") ? (
      <FolderSearch2 size={16} />
    ) : tool.tool === "create_plan" ? (
      <SquareKanban size={16} />
    ) : tool.tool.includes("pdf") ? (
      <BookAudio size={16} />
    ) : tool.tool.includes("directory") || tool.tool.includes("tree") ? (
      <FolderTree size={16} />
    ) : tool.tool === "generate_chart" || tool.tool.includes("chart") ? (
      <BarChart3 size={16} />
    ) : tool.tool.includes("mermaid") || tool.tool.includes("diagram") ? (
      <Workflow size={16} />
    ) : tool.tool.includes("requirements") ||
      tool.tool.includes("html") ||
      tool.tool.includes("prd") ||
      tool.tool.includes("ux") ? (
      <FileCode2 size={16} />
    ) : tool.tool.includes("presentation") ||
      tool.tool.includes("ppt") ||
      tool.tool.includes("slides") ? (
      <Presentation size={16} />
    ) : tool.tool.includes("web") ||
      tool.tool.includes("fetch") ||
      tool.tool.includes("browse") ||
      tool.tool.includes("url") ? (
      <Globe size={16} />
    ) : tool.tool === "terminal" ? (
      <TerminalSquare size={16} />
    ) : (
      <FileText size={16} />
    );

  const copyJson = async () => {
    if (!tool.result) return;
    await navigator.clipboard.writeText(JSON.stringify(tool.result, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  const decide = async (allow: boolean) => {
    if (!targetSessionId || deciding) return;
    setDeciding(true);
    setDecideError(null);
    try {
      const result = await request<{ ok?: boolean; message?: string }>(
        "/terminal/decide",
        {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: targetSessionId, allow }),
        }
      );
      if (result && result.ok === false) {
        setDecideError(result.message || t("tool.decideFailed", "确认失败，请重试"));
      }
    } catch (error) {
      setDecideError(
        error instanceof Error
          ? error.message
          : t("tool.decideFailed", "确认失败，请重试")
      );
    } finally {
      setDeciding(false);
    }
  };

  return (
    <div className={`tool-status-card ${tool.status}`}>
      <Flex align="center" gap={8} className="tool-status-main">
        <span className="tool-icon">
          {running ? (
            <LoadingOrb state="solving" size={20} speed={3} />
          ) : (
            icon
          )}
        </span>
        <div className="tool-copy">
          <span className="tool-name">{tool.tool}</span>
          <span className="tool-message">{statusMessage}</span>
        </div>
      </Flex>
      {tool.status === "done" && chartOption && (
        <div className="chart-block">
          <ChartBlock option={chartOption} />
        </div>
      )}
      {tool.urls && tool.urls.length > 0 && (
        <div className="tool-url-list">
          {tool.urls.map((url) => (
            <button
              key={url}
              className="tool-url-link"
              onClick={() => void openToolUrl(url)}
              title={url}
              type="button"
            >
              <Link size={13} />
              <span>{url}</span>
            </button>
          ))}
        </div>
      )}
      {tool.files && tool.files.length > 0 && (
        <div className="file-actions file-list">
          {tool.files
            .slice(0, filesOpen ? tool.files.length : 6)
            .map((file) => {
              const fileRel =
                file.path && workspacePath
                  ? toWorkspaceRelative(workspacePath, file.path)
                  : null;
              return (
                <div className="file-list-item" key={file.path ?? file.name}>
                  <a
                    className="file-download"
                    href={file.download_url ? downloadUrl(file.download_url) : "#"}
                    target="_blank"
                    rel="noreferrer"
                    title={t("tool.openDirectory", "打开所在目录")}
                    onClick={(event) => {
                      if (file.path && isTauri()) {
                        event.preventDefault();
                        void openFileLocation(file.path);
                      }
                    }}
                  >
                    {fileIcon(file)}
                    <span className="file-name">{file.name}</span>
                    {file.size != null && (
                      <span className="file-size">{formatSize(file.size)}</span>
                    )}
                    {file.path && (
                      <span className="file-path">{file.path}</span>
                    )}
                  </a>
                  {fileRel && isTauri() && (
                    <Button
                      variant="icon"
                      size="small"
                      className="file-preview-button"
                      onClick={() =>
                        onPreviewFile?.({
                          repoPath: workspacePath ?? "",
                          relPath: fileRel,
                          fileName:
                            file.path?.split("/").pop() ?? file.name,
                        })
                      }
                      title={t("tool.viewChanges", "查看改动")}
                      aria-label={t("tool.viewChanges", "查看改动")}
                    >
                      <Eye size={13} />
                    </Button>
                  )}
                </div>
              );
            })}
          {tool.files.length > 6 && !filesOpen && (
            <button
              className="file-list-more"
              type="button"
              onClick={() => setFilesOpen(true)}
            >
              {t("tool.expandFiles", "展开全部 {{count}} 个文件", {
                count: tool.files.length,
              })}
            </button>
          )}
        </div>
      )}
      {tool.status === "done" &&
        tool.result?.filepath &&
        !tool.files?.length && (
        <div className="file-actions">
          <a
            className="file-download"
            href={
              tool.result.download_url
                ? downloadUrl(tool.result.download_url)
                : "#"
            }
            target="_blank"
            rel="noreferrer"
            title={t("tool.openDirectory", "打开所在目录")}
            onClick={(event) => {
              if (tool.result?.filepath && isTauri()) {
                event.preventDefault();
                void openFileLocation(tool.result.filepath);
              }
            }}
          >
            <FolderOpen size={14} />
            <span className="file-name">{tool.result.file_name}</span>
            <span className="file-size">{formatSize(tool.result.file_size)}</span>
          </a>
          {workspaceRel && isTauri() && (
            <Button
              variant="icon"
              size="small"
              className="file-preview-button"
              onClick={() =>
                onPreviewFile?.({
                  repoPath: workspacePath ?? "",
                  relPath: workspaceRel,
                  fileName: tool.result?.file_name,
                })
              }
              title={t("tool.viewChanges", "查看改动")}
              aria-label={t("tool.viewChanges", "查看改动")}
            >
              <Eye size={13} />
            </Button>
          )}
        </div>
        )}
      {tool.status !== "confirm" &&
        (tool.commands?.length || tool.command) && (
        tool.commands?.length ? (
          <div className="terminal-commands">
            {tool.commands
              .slice(0, commandsOpen ? tool.commands.length : 3)
              .map((command) => (
              <div className="terminal-command" key={command}>
                <span className="terminal-command-prompt">$</span>
                <code>{command}</code>
              </div>
            ))}
            {tool.commands.length > 3 && !commandsOpen && (
              <button
                className="terminal-commands-more"
                type="button"
                onClick={() => setCommandsOpen(true)}
            >
              {t("tool.expandCommands", "展开全部 {{count}} 条命令", {
                count: tool.commands.length,
              })}
              </button>
            )}
          </div>
        ) : (
        <div className="terminal-command">
          <span className="terminal-command-prompt">$</span>
          <code>{tool.command}</code>
        </div>
        )
      )}
      {tool.status === "confirm" &&
        tool.confirm_type !== "external_file" &&
        tool.command && (
        <div className="terminal-confirm">
          <div className="terminal-confirm-head">
            <TerminalSquare size={14} />
            <span>{t("tool.terminalConfirm", "终端命令确认")}</span>
          </div>
          <pre>{tool.command}</pre>
          <Flex align="center" gap={8}>
            <Button size="small" loading={deciding} onClick={() => void decide(true)}>
              {t("tool.allowRun", "允许执行")}
            </Button>
            <Button
              size="small"
              variant="ghost"
              disabled={deciding}
              onClick={() => void decide(false)}
            >
              {t("tool.reject", "拒绝")}
            </Button>
          </Flex>
        </div>
      )}
      {tool.status === "confirm" && tool.confirm_type === "external_file" && (
        <div className="terminal-confirm external-file-confirm">
          <div className="terminal-confirm-head">
            <FolderOpen size={14} />
            <span>{t("tool.externalFileConfirm", "外部文件访问确认")}</span>
          </div>
          <pre>{(tool.paths ?? [tool.command]).join("\n")}</pre>
          <Flex align="center" gap={8}>
            <Button size="small" loading={deciding} onClick={() => void decide(true)}>
              {t("tool.allowAccess", "允许访问")}
            </Button>
            <Button
              size="small"
              variant="ghost"
              disabled={deciding}
              onClick={() => void decide(false)}
            >
              {t("tool.reject", "拒绝")}
            </Button>
          </Flex>
        </div>
      )}
      {tool.status === "confirm" && tool.confirm_type === "plan" && (
        <div className="terminal-confirm plan-confirm">
          <div className="terminal-confirm-head">
            <ListChecks size={14} />
            <span>{t("tool.planConfirm", "执行计划确认")}</span>
          </div>
          <p className="plan-confirm-text">
            {t("tool.planConfirmText", "计划已创建，是否开始执行？")}
          </p>
          <Flex align="center" gap={8}>
            <Button
              size="small"
              loading={deciding}
              disabled={!targetSessionId || deciding}
              onClick={() => void decide(true)}
            >
              {t("tool.startExecution", "开始执行")}
            </Button>
            <Button
              size="small"
              variant="ghost"
              disabled={!targetSessionId || deciding}
              onClick={() => void decide(false)}
            >
              {t("common.cancel", "取消")}
            </Button>
          </Flex>
        </div>
      )}
      {tool.status === "confirm" && tool.confirm_type === "plan_choice" && (
        <div className="terminal-confirm plan-choice-confirm">
          <div className="terminal-confirm-head">
            <ListChecks size={14} />
            <span>{t("tool.planChoiceConfirm", "方案确认")}</span>
          </div>
          <p className="plan-confirm-text">
            {t("tool.planChoiceText", "执行任务前是否先出一份方案？")}
          </p>
          <Flex align="center" gap={8}>
            <Button
              size="small"
              loading={deciding}
              onClick={() => void decide(true)}
            >
              {t("tool.planFirst", "先出方案")}
            </Button>
            <Button
              size="small"
              variant="ghost"
              disabled={deciding}
              onClick={() => void decide(false)}
            >
              {t("tool.executeDirectly", "直接执行")}
            </Button>
          </Flex>
        </div>
      )}
      {tool.status === "confirm" && tool.confirm_type === "write_calendar" && (
        <div className="terminal-confirm calendar-confirm">
          <div className="terminal-confirm-head">
            <CalendarDays size={14} />
            <span>{t("tool.calendarConfirm", "写入日程确认")}</span>
          </div>
          <p className="plan-confirm-text">
            {t("tool.calendarConfirmText", "是否同时写入日程？")}
          </p>
          <Flex align="center" gap={8}>
            <Button size="small" loading={deciding} onClick={() => void decide(true)}>
              {t("tool.writeCalendar", "写入日程")}
            </Button>
            <Button
              size="small"
              variant="ghost"
              disabled={deciding}
              onClick={() => void decide(false)}
            >
              {t("common.cancel", "取消")}
            </Button>
          </Flex>
        </div>
      )}
      {tool.status === "confirm" && tool.confirm_type === "skill_migrate" && (
        <div className="terminal-confirm skill-migrate-confirm">
          <div className="terminal-confirm-head">
            <FileCode2 size={14} />
            <span>{t("tool.skillMigrateConfirm", "技能迁移确认")}</span>
          </div>
          <div className="skill-migrate-meta">
            <span className="skill-migrate-name">
              {tool.skill_migrate?.name ?? tool.message}
            </span>
            <span>
              {t("tool.sourceTarget", "来源：{{source}} · 目标：{{target}}", {
                source: tool.skill_migrate?.source_tool ?? t("tool.unknown", "未知"),
                target:
                  tool.target === "user"
                    ? t("tool.targetUser", "用户级 ~/.divine/skills")
                    : t("tool.targetProject", "项目 .divine/skills"),
              })}
            </span>
            {tool.skill_migrate?.description && (
              <span className="skill-migrate-description">
                {tool.skill_migrate.description}
              </span>
            )}
          </div>
          <pre>{tool.skill_migrate?.preview ?? tool.message}</pre>
          <Flex align="center" gap={8}>
            <Button
              size="small"
              loading={deciding}
              disabled={!targetSessionId || deciding}
              onClick={() => void decide(true)}
            >
              {t("tool.confirmMigrate", "确认迁移")}
            </Button>
            <Button
              size="small"
              variant="ghost"
              disabled={!targetSessionId || deciding}
              onClick={() => void decide(false)}
            >
              {t("common.cancel", "取消")}
            </Button>
          </Flex>
        </div>
      )}
      {tool.status === "confirm" &&
        tool.confirm_type === "skill_migrate_batch" && (
        <div className="terminal-confirm skill-migrate-confirm">
          <div className="terminal-confirm-head">
            <FileCode2 size={14} />
            <span>{t("tool.batchMigrateConfirm", "批量技能迁移确认")}</span>
          </div>
          <div className="skill-migrate-meta">
            <span className="skill-migrate-name">
              {t("tool.skillsToMigrate", "{{count}} 个技能待迁移", {
                count: tool.skill_migrations?.length ?? 0,
              })}
            </span>
            <span>
              {t("tool.targetLabel", "目标：{{target}}", {
                target:
                  tool.target === "user"
                    ? t("tool.targetUser", "用户级 ~/.divine/skills")
                    : t("tool.targetProject", "项目 .divine/skills"),
              })}
            </span>
          </div>
          <div className="skill-migration-list">
            {tool.skill_migrations?.map((skill) => (
              <div className="skill-migration-item" key={skill.name}>
                <span className="skill-migration-item-name">
                  {skill.name}
                </span>
                <span className="skill-migration-item-source">
                  {skill.source_tool}
                </span>
                {skill.existing && (
                  <span className="skill-migration-item-existing">
                    {t("tool.existingSkip", "已存在，将跳过")}
                  </span>
                )}
                {skill.description && (
                  <span className="skill-migration-item-description">
                    {skill.description}
                  </span>
                )}
              </div>
            ))}
          </div>
          <pre>
            {tool.skill_migrations
              ?.map(
                (skill) =>
                  `## ${skill.name} (${skill.source_tool})\n${skill.preview}`
              )
              .join("\n\n---\n\n") ?? tool.message}
          </pre>
          <Flex align="center" gap={8}>
            <Button
              size="small"
              loading={deciding}
              disabled={!targetSessionId || deciding}
              onClick={() => void decide(true)}
            >
              {t("tool.confirmAllMigrate", "确认全部迁移")}
            </Button>
            <Button
              size="small"
              variant="ghost"
              disabled={!targetSessionId || deciding}
              onClick={() => void decide(false)}
            >
              {t("common.cancel", "取消")}
            </Button>
          </Flex>
        </div>
      )}
      {tool.status === "confirm" && tool.confirm_type === "skill_install" && (
        <div className="terminal-confirm skill-migrate-confirm">
          <div className="terminal-confirm-head">
            <FileCode2 size={14} />
            <span>{t("tool.gitHubInstallConfirm", "GitHub 技能安装确认")}</span>
          </div>
          <div className="skill-migrate-meta">
            <span className="skill-migrate-name">
              {tool.skill_install?.skills?.[0]?.name ?? tool.skill_install?.repo ?? tool.message}
            </span>
            <span>
              {t("tool.repoTarget", "仓库：{{repo}} · 目标：{{target}}", {
                repo: tool.skill_install?.repo ?? t("tool.unknown", "未知"),
                target:
                  tool.target === "user"
                    ? t("tool.targetUser", "用户级 ~/.divine/skills")
                    : t("tool.targetProject", "项目 .divine/skills"),
              })}
            </span>
            {tool.skill_install && tool.skill_install.skills.length > 1 && (
              <span>
                {t("tool.repoContains", "仓库包含 {{count}} 个技能：", {
                  count: tool.skill_install.skills.length,
                })}
                {tool.skill_install.skills
                  .map(
                    (skill) =>
                      `${skill.name} (${skill.skill_path || t("tool.repoRoot", "仓库根目录")})`
                  )
                  .join(t("tasks.dayJoin", "、"))}
              </span>
            )}
            {tool.skill_install?.skills?.[0]?.description && (
              <span className="skill-migrate-description">
                {tool.skill_install.skills[0].description}
              </span>
            )}
          </div>
          <pre>
            {tool.skill_install?.skills?.[0]?.preview ?? tool.message}
          </pre>
          <Flex align="center" gap={8}>
            <Button
              size="small"
              loading={deciding}
              disabled={!targetSessionId || deciding}
              onClick={() => void decide(true)}
            >
              {t("tool.confirmInstall", "确认安装")}
            </Button>
            <Button
              size="small"
              variant="ghost"
              disabled={!targetSessionId || deciding}
              onClick={() => void decide(false)}
            >
              {t("common.cancel", "取消")}
            </Button>
          </Flex>
        </div>
      )}
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
                : tool.result.message ?? ""}
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
              onClick={() =>
                window.dispatchEvent(new CustomEvent("divine:open-tasks"))
              }
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
}

function chartOptionFromResult(
  result?: ToolEvent["result"]
): Record<string, unknown> | null {
  const data = result?.data;
  if (data && data.option && typeof data.option === "object") {
    return data.option as Record<string, unknown>;
  }
  if (result?.option && typeof result.option === "object") {
    return result.option as Record<string, unknown>;
  }
  return null;
}

const GROUPABLE_TOOLS = new Set([
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
  "write_file",
  "search_files",
  "directory_tree",
  "terminal",
]);

function groupToolCards(tools: ToolEvent[]): ToolEvent[] {
  const grouped: ToolEvent[] = [];
  for (const tool of tools) {
    if (!GROUPABLE_TOOLS.has(tool.tool)) {
      grouped.push(tool);
      continue;
    }
    const index = grouped.findIndex((item) => item.tool === tool.tool);
    if (index === -1) {
      grouped.push({
        ...tool,
        count: 1,
        urls: toolUrls(tool),
        files: toolFiles(tool),
        commands: toolCommands(tool),
      });
      continue;
    }
    const existing = grouped[index];
    const count = (existing.count ?? 1) + 1;
    const urls = [...new Set([...(existing.urls ?? []), ...toolUrls(tool)])];
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
        tool.tool === "web_fetch" || tool.tool === "web_fetch_batch"
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
              : i18next.t("tool.executedTimes", "{{tool}} 已执行 {{count}} 次", {
                  tool: tool.tool.toUpperCase(),
                  count,
                }),
    };
  }
  return grouped;
}

function toolUrls(tool: ToolEvent): string[] {
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

function toolFiles(tool: ToolEvent): ToolFileLink[] {
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

function toolCommands(tool: ToolEvent): string[] {
  if (tool.commands?.length) return tool.commands;
  return tool.command ? [tool.command] : [];
}

function fileIcon(file: ToolFileLink): ReactNode {
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

async function openToolUrl(url: string): Promise<void> {
  if (isTauri()) {
    await openUrl(url);
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

function chartTypeIcon(option: Record<string, unknown>): ReactNode {
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

function isChartSeries(
  value: unknown
): value is Record<string, unknown> & { type?: unknown } {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    "type" in value
  );
}
