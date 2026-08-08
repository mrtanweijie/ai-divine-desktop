import { useMemo } from "react";
import { Plus, Settings } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Flex } from "@/components/ui/Flex";
import type { Session } from "@/types";
import { groupLabel } from "@/utils";
import { SessionListItem } from "./SessionListItem";

interface SessionListProps {
  sessions: Session[];
  selectedId: string | null;
  collapsed: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onOpenSettings: () => void;
}

export function SessionList({
  sessions,
  selectedId,
  collapsed,
  onSelect,
  onNew,
  onRename,
  onDelete,
  onOpenSettings,
}: SessionListProps) {
  const groups = useMemo(() => {
    const labels = ["今天", "昨天", "更早"];
    return labels
      .map((label) => ({
        label,
        items: sessions.filter(
          (session) => groupLabel(session.updated_at) === label
        ),
      }))
      .filter((group) => group.items.length > 0);
  }, [sessions]);

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
        <Button
          variant="secondary"
          size="small"
          className="new-chat-button"
          onClick={onNew}
        >
          <Plus size={16} aria-hidden="true" />
          <span>新建对话</span>
        </Button>
        </Flex>

        <nav className="session-list" aria-label="会话">
          {groups.length === 0 && (
            <EmptyState title="还没有会话" />
          )}
          {groups.map((group) => (
            <section className="session-group" key={group.label}>
              <h2 className="session-group-title">{group.label}</h2>
              {group.items.map((session) => (
                <SessionListItem
                  key={session.id}
                  session={session}
                  active={session.id === selectedId}
                  onSelect={onSelect}
                  onRename={onRename}
                  onDelete={onDelete}
                />
              ))}
            </section>
          ))}
        </nav>

        <Button
          variant="ghost"
          className="settings-link"
          onClick={onOpenSettings}
        >
          <Settings size={15} />
          <span>设置</span>
        </Button>
      </div>
    </aside>
  );
}
