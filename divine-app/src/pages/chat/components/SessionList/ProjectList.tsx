import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  FolderOpen,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Settings,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import type { Project, Session } from "@/types";
import { formatTime } from "@/utils";
import { openFolder } from "@/services/tauri";
import { ProjectIcon } from "@/pages/chat/components/ProjectIcon";

interface ProjectListProps {
  projects: Project[];
  sessions: Session[];
  selectedProjectId: string | null;
  selectedId: string | null;
  selectionActive: boolean;
  onSelectProject: (id: string) => void;
  onNewProject: () => void;
  onNewConversation: (id: string) => void;
  onRenameProject: (project: Project) => void;
  onDeleteProject: (id: string) => void;
  onSelectSession: (id: string) => void;
  onRenameSession: (id: string, title: string) => void;
  onDeleteSession: (id: string) => void;
}

export function ProjectList({
  projects,
  sessions,
  selectedProjectId,
  selectedId,
  selectionActive,
  onSelectProject,
  onNewProject,
  onNewConversation,
  onRenameProject,
  onDeleteProject,
  onSelectSession,
  onRenameSession,
  onDeleteSession,
}: ProjectListProps) {
  const { t } = useTranslation();
  return (
    <section
      className="project-section"
      aria-label={t("session.projects", "项目")}
    >
      <div className="project-header">
        <span className="sidebar-section-label">
          {t("session.projects", "项目")}
        </span>
        <Button
          variant="icon"
          size="small"
          className="project-add-button"
          onClick={onNewProject}
          title={t("session.newProject", "新建项目")}
          aria-label={t("session.newProject", "新建项目")}
        >
          <Plus size={14} />
        </Button>
      </div>
      <div className="project-list">
        {projects.map((project) => (
          <ProjectBranch
            key={project.id}
            project={project}
            active={selectionActive && project.id === selectedProjectId}
            selectedId={selectedId}
            selectionActive={selectionActive}
            projectSessions={sessions.filter(
              (session) => session.project_id === project.id
            )}
            onSelectProject={onSelectProject}
            onNewConversation={onNewConversation}
            onRenameProject={onRenameProject}
            onDeleteProject={onDeleteProject}
            onSelectSession={onSelectSession}
            onRenameSession={onRenameSession}
            onDeleteSession={onDeleteSession}
          />
        ))}
      </div>
    </section>
  );
}

interface ProjectBranchProps {
  project: Project;
  active: boolean;
  selectedId: string | null;
  selectionActive: boolean;
  projectSessions: Session[];
  onSelectProject: (id: string) => void;
  onNewConversation: (id: string) => void;
  onRenameProject: (project: Project) => void;
  onDeleteProject: (id: string) => void;
  onSelectSession: (id: string) => void;
  onRenameSession: (id: string, title: string) => void;
  onDeleteSession: (id: string) => void;
}

function ProjectBranch({
  project,
  active,
  selectedId,
  selectionActive,
  projectSessions,
  onSelectProject,
  onNewConversation,
  onRenameProject,
  onDeleteProject,
  onSelectSession,
  onRenameSession,
  onDeleteSession,
}: ProjectBranchProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const visibleSessions = expanded
    ? projectSessions
    : projectSessions.slice(0, 5);

  return (
    <div className={`project-branch${active ? " active" : ""}`}>
      <ProjectItem
        project={project}
        active={active}
        onSelect={(id) => {
          setExpanded(false);
          onSelectProject(id);
        }}
        onNewConversation={onNewConversation}
        onRename={onRenameProject}
        onDelete={onDeleteProject}
      />
      <div className="project-sessions">
        {projectSessions.length === 0 ? (
          <div className="project-session-empty">
            {t("session.emptyProjectSessions", "该项目还没有会话")}
          </div>
        ) : (
          <>
            {visibleSessions.map((session) => (
              <ProjectSessionItem
                key={session.id}
                session={session}
                active={selectionActive && session.id === selectedId}
                onSelect={onSelectSession}
                onRename={onRenameSession}
                onDelete={onDeleteSession}
              />
            ))}
            {!expanded && projectSessions.length > 5 && (
              <div
                className="project-sessions-expand"
                role="button"
                tabIndex={0}
                onClick={() => setExpanded(true)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    setExpanded(true);
                    event.currentTarget.blur();
                  }
                }}
              >
                <span>{t("session.expand", "展开显示")}</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

interface ProjectItemProps {
  project: Project;
  active: boolean;
  onSelect: (id: string) => void;
  onNewConversation: (id: string) => void;
  onRename: (project: Project) => void;
  onDelete: (id: string) => void;
}

function ProjectItem({
  project,
  active,
  onSelect,
  onNewConversation,
  onRename,
  onDelete,
}: ProjectItemProps) {
  const [actionOpen, setActionOpen] = useState(false);

  return (
    <Flex
      align="center"
      gap={8}
      className={`project-item ${active ? "active" : ""}${
        actionOpen ? " action-open" : ""
      }`}
      title={project.path}
      onClick={(event) => {
        onSelect(project.id);
        event.currentTarget.blur();
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          onSelect(project.id);
          event.currentTarget.blur();
        }
      }}
    >
      <ProjectIcon
        icon={project.icon}
        size={13}
        className="project-folder-icon"
      />
      <div className="project-copy">
        <span className="project-name">{project.name}</span>
      </div>
      <div className="project-actions">
        <ProjectActionMenu
          project={project}
          onNewConversation={() => onNewConversation(project.id)}
          onRename={() => onRename(project)}
          onDelete={() => onDelete(project.id)}
          onOpenChange={setActionOpen}
        />
      </div>
    </Flex>
  );
}

interface ProjectActionMenuProps {
  project: Project;
  onNewConversation: () => void;
  onRename: () => void;
  onDelete: () => void;
  onOpenChange: (open: boolean) => void;
}

function ProjectActionMenu({
  project,
  onNewConversation,
  onRename,
  onDelete,
  onOpenChange,
}: ProjectActionMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [style, setStyle] = useState<CSSProperties>({});
  const triggerRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<number | null>(null);

  const cancelClose = () => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  const scheduleClose = () => {
    cancelClose();
    closeTimer.current = window.setTimeout(() => {
      setOpen(false);
    }, 180);
  };

  useEffect(() => {
    onOpenChange(open);
  }, [onOpenChange, open]);

  useEffect(() => {
    return () => {
      if (closeTimer.current !== null) {
        window.clearTimeout(closeTimer.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!open || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setStyle({
      position: "fixed",
      top: rect.bottom + 4,
      left: rect.right,
    });
    const closeOnOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (!target?.closest(".project-action-picker")) {
        setOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <>
      <div
        ref={triggerRef}
        className="project-action-trigger"
        role="button"
        tabIndex={0}
        title={t("session.projectActions", "项目操作")}
        aria-label={t("session.projectActionsFor", "{{name}} 项目操作", {
          name: project.name,
        })}
        onMouseEnter={() => {
          cancelClose();
          setOpen(true);
        }}
        onMouseLeave={scheduleClose}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.stopPropagation();
            setOpen((value) => !value);
          }
        }}
      >
        <MoreHorizontal size={13} />
      </div>
      {open &&
        createPortal(
          <div className="project-action-picker" style={style} role="menu">
            <div
              className="project-action-hover-zone"
              onMouseEnter={cancelClose}
              onMouseLeave={scheduleClose}
            >
            <button
              type="button"
              role="menuitem"
              className="project-action-item"
              onClick={(event) => {
                event.stopPropagation();
                setOpen(false);
                onNewConversation();
              }}
            >
              <Plus size={13} />
              <span>{t("session.newConversation", "新建对话")}</span>
            </button>
            <div
              className="project-action-item project-action-count"
              role="presentation"
            >
              <MessageSquare size={13} />
              <span>
                {t("session.sessionCount", "{{count}} 个对话", {
                  count: project.session_count ?? 0,
                })}
              </span>
            </div>
            <button
              type="button"
              role="menuitem"
              className="project-action-item project-action-path"
              onClick={(event) => {
                event.stopPropagation();
                setOpen(false);
                void openFolder(project.path);
              }}
            >
              <FolderOpen size={13} />
              <span>{project.path}</span>
            </button>
            <button
              type="button"
              role="menuitem"
              className="project-action-item"
              onClick={(event) => {
                event.stopPropagation();
                setOpen(false);
                onRename();
              }}
            >
              <Settings size={13} />
              <span>{t("session.editProject", "编辑项目")}</span>
            </button>
            <button
              type="button"
              role="menuitem"
              className="project-action-item"
              onClick={(event) => {
                event.stopPropagation();
                setOpen(false);
                onDelete();
              }}
            >
              <Trash2 size={13} />
              <span>{t("session.deleteProject", "删除项目")}</span>
            </button>
            </div>
          </div>,
          document.body
        )}
    </>
  );
}

interface ProjectSessionItemProps {
  session: Session;
  active: boolean;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}

function ProjectSessionItem({
  session,
  active,
  onSelect,
  onRename,
  onDelete,
}: ProjectSessionItemProps) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session.title);

  const commitRename = () => {
    if (title.trim()) {
      onRename(session.id, title.trim());
    }
    setEditing(false);
  };

  return (
    <Flex
      align="center"
      gap={6}
      className={`project-session-item ${active ? "active" : ""}`}
      onClick={(event) => {
        onSelect(session.id);
        event.currentTarget.blur();
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          onSelect(session.id);
          event.currentTarget.blur();
        }
      }}
    >
      {editing ? (
        <Input
          className="project-session-rename-input"
          value={title}
          autoFocus
          onChange={(event) => setTitle(event.target.value)}
          onBlur={commitRename}
          onKeyDown={(event) => {
            if (event.key === "Enter") commitRename();
            if (event.key === "Escape") {
              setTitle(session.title);
              setEditing(false);
            }
          }}
          onClick={(event) => event.stopPropagation()}
        />
      ) : (
        <>
          <div className="project-session-copy">
            <span className="project-session-title">{session.title}</span>
            <span className="project-session-time">
              {formatTime(session.updated_at)}
            </span>
          </div>
          <div className="project-session-actions">
            <Button
              variant="icon"
              size="small"
              title={t("session.rename", "重命名")}
              aria-label={t("session.rename", "重命名")}
              onClick={(event) => {
                event.stopPropagation();
                setEditing(true);
              }}
            >
              <Pencil size={12} />
            </Button>
            <Button
              variant="icon"
              size="small"
              title={t("session.delete", "删除")}
              aria-label={t("session.deleteSession", "删除会话")}
              onClick={(event) => {
                event.stopPropagation();
                onDelete(session.id);
              }}
            >
              <Trash2 size={12} />
            </Button>
          </div>
        </>
      )}
    </Flex>
  );
}
