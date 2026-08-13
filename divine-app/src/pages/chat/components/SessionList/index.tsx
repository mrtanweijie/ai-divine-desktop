import {
  Clock,
  MessageSquareQuote,
  Settings,
  Sparkles,
} from "lucide-react";
import { Flex } from "@/components/ui/Flex";
import type { Project, Session } from "@/types";
import { ProjectList } from "./ProjectList";

interface SessionListProps {
  sessions: Session[];
  projects: Project[];
  selectedId: string | null;
  selectedProjectId: string | null;
  collapsed: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onSelectProject: (id: string) => void;
  onNewProject: () => void;
  onNewConversationInProject: (id: string) => void;
  onRenameProject: (project: Project) => void;
  onDeleteProject: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onOpenSettings: () => void;
  onOpenTasks: () => void;
  onOpenSkills: () => void;
  activeView: "chat" | "tasks" | "skills";
  model: string;
}

export function SessionList({
  sessions,
  projects,
  selectedId,
  selectedProjectId,
  collapsed,
  onSelect,
  onNew,
  onSelectProject,
  onNewProject,
  onNewConversationInProject,
  onRenameProject,
  onDeleteProject,
  onRename,
  onDelete,
  onOpenSettings,
  onOpenTasks,
  onOpenSkills,
  activeView,
  model,
}: SessionListProps) {
  return (
    <aside
      className={`session-sidebar${collapsed ? " collapsed" : ""}`}
      aria-label="会话列表"
    >
      <div
        className="session-sidebar-content"
        style={collapsed ? { display: "none" } : undefined}
      >
        <Flex align="center" gap={8} className="sidebar-header">
          <div
            className="new-chat-link"
            role="button"
            tabIndex={0}
            onClick={() => onNew()}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                onNew();
                event.currentTarget.blur();
              }
            }}
          >
            <MessageSquareQuote size={16} aria-hidden="true" />
            <span>新对话</span>
          </div>
        </Flex>

        <div
          className={`tasks-link tasks-nav-link${
            activeView === "tasks" ? " active" : ""
          }`}
          role="button"
          tabIndex={0}
          onClick={onOpenTasks}
          title="已安排"
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              onOpenTasks();
              event.currentTarget.blur();
            }
          }}
        >
          <Clock size={15} />
          <span>已安排</span>
        </div>

        <div
          className={`tasks-link skills-nav-link${
            activeView === "skills" ? " active" : ""
          }`}
          role="button"
          tabIndex={0}
          onClick={onOpenSkills}
          title="技能"
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              onOpenSkills();
              event.currentTarget.blur();
            }
          }}
        >
          <Sparkles size={15} />
          <span>技能</span>
        </div>

        <ProjectList
          projects={projects}
          sessions={sessions}
          selectedProjectId={selectedProjectId}
          selectedId={selectedId}
          selectionActive={activeView === "chat"}
          onSelectProject={onSelectProject}
          onNewProject={onNewProject}
          onNewConversation={onNewConversationInProject}
          onRenameProject={onRenameProject}
          onDeleteProject={onDeleteProject}
          onSelectSession={onSelect}
          onRenameSession={onRename}
          onDeleteSession={onDelete}
        />

        <div className="settings-footer">
          <div
            className="settings-link"
            role="button"
            tabIndex={0}
            onClick={onOpenSettings}
            title="设置"
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                onOpenSettings();
                event.currentTarget.blur();
              }
            }}
          >
            <Settings size={15} />
            <span>{model || "本地演示"}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
