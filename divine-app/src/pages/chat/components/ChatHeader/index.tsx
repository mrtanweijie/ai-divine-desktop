import { useEffect, useState } from "react";
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
import type { Project, Session } from "@/types";
import { exportSession } from "@/services/api";
import { ProjectIcon } from "@/pages/chat/components/ProjectIcon";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { isTauri } from "@/services/tauri";

interface ChatHeaderProps {
  session: Session | null;
  project: Project | null;
  onOpenSidebar: () => void;
  onRename: (id: string, title: string) => void;
  workspaceOpen: boolean;
  onToggleWorkspace: () => void;
}

export function ChatHeader({
  session,
  project,
  onOpenSidebar,
  onRename,
  workspaceOpen,
  onToggleWorkspace,
}: ChatHeaderProps) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session?.title ?? "新对话");

  useEffect(() => {
    setTitle(session?.title ?? "新对话");
  }, [session?.title]);

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
          aria-label="打开会话列表"
          title="会话列表"
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
            aria-label="会话标题"
          />
        ) : (
          <Button
            variant="ghost"
            className="title-button"
            onClick={() => {
              setTitle(session?.title ?? "新对话");
              setEditing(true);
            }}
            title="点击重命名"
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
        {session && (
          <Dropdown
            label="导出会话"
            align="center"
            trigger={
              <Button variant="icon" title="导出会话">
                <Download size={15} />
              </Button>
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
                label: "文本",
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
        {!workspaceOpen && (
          <Button
            variant="icon"
            className="workspace-toggle"
            onClick={onToggleWorkspace}
            title="打开文件面板"
            aria-label="打开文件面板"
          >
            <PanelRightOpen size={15} />
          </Button>
        )}
      </Flex>
    </header>
  );
}
