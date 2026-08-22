// Renders a single tool status card, including approvals and file actions.
import { useMemo, useState } from "react";
import {
  AlertCircle,
  BarChart3,
  BookAudio,
  BookMarked,
  BookOpenCheck,
  BookSearch,
  Box,
  Calculator,
  CalendarClock,
  CalendarDays,
  Check,
  ChevronDown,
  Copy,
  Database,
  Eye,
  FileBox,
  FileCode2,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  FolderSearch2,
  FolderTree,
  GitBranch,
  GitBranchMinus,
  GitCommit,
  GitCommitHorizontal,
  GitCompareArrows,
  GitGraph,
  Globe,
  Group,
  Image,
  ImageDown,
  LibraryBig,
  Link,
  ListChecks,
  Orbit,
  Package,
  PenTool,
  Presentation,
  SquareKanban,
  StickyNote,
  TerminalSquare,
  Workflow,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import { ChartBlock } from "@/pages/chat/components/ChartBlock";
import { downloadUrl } from "@/services/api";
import { request } from "@/services/request";
import { isTauri, openFileLocation } from "@/services/tauri";
import { toWorkspaceRelative } from "@/services/workspace";
import type { PreviewFile, ToolEvent } from "@/types";
import { copyText, formatSize } from "@/utils";
import {
  chartOptionFromResult,
  chartTypeIcon,
  fileIcon,
  openToolUrl,
} from "./MessageHelpers";
import { DiffView } from "./DiffView";

export function ToolStatusCard({
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
  const [urlsOpen, setUrlsOpen] = useState(false);
  const targetSessionId = tool.session_id ?? sessionId;
  const running = tool.status === "running" || tool.status === "preparing";
  const urls = tool.urls ?? [];
  const hasUrls = urls.length > 0;
  const toggleUrls = () => setUrlsOpen((value) => !value);
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
    ) : tool.tool === "run_subagents" ? (
      <GitGraph size={16} />
    ) : tool.tool === "git_status" ? (
      <GitBranch size={16} />
    ) : tool.tool === "git_diff" ? (
      <GitCompareArrows size={16} />
    ) : tool.tool === "git_log" ? (
      <GitCommitHorizontal size={16} />
    ) : tool.tool === "git_commit" ? (
      <GitCommit size={16} />
    ) : tool.tool === "git_revert" ? (
      <GitBranchMinus size={16} />
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
    ) : tool.tool.includes("grep") ? (
      <BookOpenCheck size={16} />
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
    ) : tool.tool === "web_fetch_batch" ? (
      <Package size={16} />
    ) : tool.tool === "web_fetch" ? (
      <Box size={16} />
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
    await copyText(JSON.stringify(tool.result, null, 2));
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
      <Flex
        align="center"
        gap={8}
        className={`tool-status-main${hasUrls ? " clickable" : ""}`}
        onClick={hasUrls ? toggleUrls : undefined}
        role={hasUrls ? "button" : undefined}
        tabIndex={hasUrls ? 0 : undefined}
        aria-expanded={hasUrls ? urlsOpen : undefined}
        onKeyDown={
          hasUrls
            ? (event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  toggleUrls();
                }
              }
            : undefined
        }
      >
        <span className="tool-icon">
          {running ? (
            <LoadingOrb state="solving" size={20} speed={3} />
          ) : (
            icon
          )}
        </span>
        <div className="tool-copy">
          <span className="tool-name">{tool.tool}</span>
          <span
            className={`tool-message${
              tool.status === "running" && tool.currentUrl ? " nowrap" : ""
            }`}
          >
            {statusMessage}
          </span>
        </div>
        {hasUrls && (
          <>
            <span className="tool-url-count">
              {t("tool.urlCount", "{{count}} 个链接", {
                count: urls.length,
              })}
            </span>
            <ChevronDown
              size={14}
              className={`tool-url-chevron${urlsOpen ? " expanded" : ""}`}
            />
          </>
        )}
      </Flex>
      {tool.status === "done" && chartOption && (
        <div className="chart-block">
          <ChartBlock option={chartOption} />
        </div>
      )}
      {hasUrls && urlsOpen && (
        <div className="tool-url-list">
          {urls.map((url) => (
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
      {tool.tool === "edit_files" &&
        tool.status === "done" &&
        typeof tool.result?.data?.diff === "string" &&
        tool.result.data.diff.trim().length > 0 && (
          <DiffView diff={tool.result.data.diff} />
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
      {tool.status === "confirm" && tool.confirm_type === "subagents_write" && (
        <div className="terminal-confirm subagents-write-confirm">
          <div className="terminal-confirm-head">
            <Group size={14} />
            <span>{t("tool.subagentsWriteConfirm", "并行写任务确认")}</span>
          </div>
          <p className="plan-confirm-text">
            {t("tool.subagentsWriteText", "以下子任务将并行创建/修改文件，是否确认执行？")}
          </p>
          <div className="subagents-write-list">
            {tool.subagent_write?.tasks.map((task) => (
              <div className="subagents-write-item" key={task.id}>
                <span className="subagents-write-item-name">
                  {task.name}
                </span>
                <span className="subagents-write-item-paths">
                  {(task.write_paths ?? []).join(", ") ||
                    t("tool.unknown", "未知")}
                </span>
              </div>
            ))}
          </div>
          <Flex align="center" gap={8}>
            <Button
              size="small"
              loading={deciding}
              disabled={!targetSessionId || deciding}
              onClick={() => void decide(true)}
            >
              {t("tool.confirmWrite", "确认执行")}
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
