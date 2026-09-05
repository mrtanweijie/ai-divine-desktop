import { memo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronLeft,
  Download,
  File,
  FileText,
  FileType,
  PanelRightOpen,
  Pencil,
  PanelLeftOpen,
} from "lucide-react";
import type { PreviewFile, Project, Session } from "@/types";
import { exportSession } from "@/services/api";
import { ProjectIcon } from "@/pages/chat/components/ProjectIcon";
import { GitInfoCard } from "@/pages/chat/components/GitInfoCard";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import { Dropdown } from "@/components/ui/Dropdown";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { Tooltip } from "@/components/ui/Tooltip";
import { isTauri } from "@/services/tauri";
import { formatTokens } from "@/utils";

import "./index.less";
interface ChatHeaderProps {
  session: Session | null;
  project: Project | null;
  onOpenSidebar: () => void;
  onRename: (id: string, title: string) => void;
  workspaceOpen: boolean;
  onToggleWorkspace: () => void;
  onPreviewFile?: (file: PreviewFile) => void;
  isGit?: boolean;
  /** 会话累计 token 消耗（来自每条回复的 token_usage 汇总） */
  tokenUsage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    turns: number;
  };
}

export function ChatHeaderInner({
  session,
  project,
  onOpenSidebar,
  onRename,
  workspaceOpen,
  onToggleWorkspace,
  onPreviewFile,
  isGit = false,
  tokenUsage,
}: ChatHeaderProps) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session?.title ?? t("session.newChat", "新对话"));

  // 会话标题变化时同步本地编辑态：渲染期调整（替代 effect 内 setState）
  const [prevTitle, setPrevTitle] = useState(session?.title);
  if (prevTitle !== session?.title) {
    setPrevTitle(session?.title);
    setTitle(session?.title ?? t("session.newChat", "新对话"));
  }

  const commitTitle = () => {
    if (session && title.trim()) {
      onRename(session.id, title.trim());
    }
    setEditing(false);
  };

  return (
    <header className="chat-header">
      <Flex align="center" gap={8} className="chat-header-left">
        <Button
          variant="icon"
          className="mobile-sidebar-button"
          onClick={onOpenSidebar}
          aria-label={t("chat.openSessionList", "打开会话列表")}
          title={t("session.list", "会话列表")}
        >
          <PanelLeftOpen size={16} />
        </Button>
        <ChevronLeft size={16} className="back-icon" aria-hidden="true" />
        {editing ? (
          <Input
            className="title-input"
            value={title}
            autoFocus
            onChange={(event) => setTitle(event.target.value)}
            onBlur={commitTitle}
            onKeyDown={(event) => {
              if (event.key === "Enter") commitTitle();
              if (event.key === "Escape") {
                setTitle(session?.title ?? "");
                setEditing(false);
              }
            }}
            aria-label={t("session.titleLabel", "会话标题")}
          />
        ) : (
          <Button
            variant="ghost"
            className="title-button"
            onClick={() => {
              setTitle(session?.title ?? t("session.newChat", "新对话"));
              setEditing(true);
            }}
            title={t("session.clickToRename", "点击重命名")}
          >
            <span
              className="session-title-text"
              {...(isTauri() ? { "data-tauri-drag-region": true } : {})}
            >
              {title}
            </span>
            <Pencil size={13} className="title-pencil" aria-hidden="true" />
          </Button>
        )}
      </Flex>

      <div
        className="chat-header-drag"
        {...(isTauri() ? { "data-tauri-drag-region": true } : {})}
      />

      <Flex align="center" gap={6} className="chat-header-right">
        {session && tokenUsage && tokenUsage.total_tokens > 0 && (
          <Tooltip
            placement="bottom"
            align="right"
            content={t(
              "session.tokenUsageTotal",
              "本会话累计消耗 {{total}} tokens（输入 {{input}} · 输出 {{output}} · 共 {{turns}} 轮）",
              {
                total: formatTokens(tokenUsage.total_tokens),
                input: formatTokens(tokenUsage.input_tokens),
                output: formatTokens(tokenUsage.output_tokens),
                turns: tokenUsage.turns,
              },
            )}
          >
            <span className="chat-header-token-usage">
              {t("session.tokenUsageShort", "{{count}} tokens", {
                value: formatTokens(tokenUsage.total_tokens),
              })}
            </span>
          </Tooltip>
        )}
        {session && (
          <Dropdown
            label={t("chat.exportSession", "导出会话")}
            align="center"
            trigger={
              <IconButton
                icon={<Download size={13} />}
                title={t("chat.exportSession", "导出会话")}
              />
            }
            items={[
              {
                key: "markdown",
                label: "Markdown",
                icon: <FileType size={13} />,
                onClick: () => exportSession(session.id, "markdown"),
              },
              {
                key: "pdf",
                label: "PDF",
                icon: <FileText size={13} />,
                onClick: () => exportSession(session.id, "pdf"),
              },
              {
                key: "text",
                label: t("chat.text", "文本"),
                icon: <File size={13} />,
                onClick: () => exportSession(session.id, "text"),
              },
            ]}
          />
        )}
        {project && (
          <span className="project-badge" title={project.path}>
            <ProjectIcon icon={project.icon} size={12} />
            <span className="project-badge-name">{project.name}</span>
          </span>
        )}
        {project && isGit && (
          <GitInfoCard projectPath={project.path} onPreviewFile={onPreviewFile} />
        )}
        {!workspaceOpen && (
          <IconButton
            icon={<PanelRightOpen size={13} />}
            title={t("chat.openFilePanel", "打开文件面板")}
            onClick={onToggleWorkspace}
          />
        )}
      </Flex>
    </header>
  );
}

export const ChatHeader = memo(ChatHeaderInner);
