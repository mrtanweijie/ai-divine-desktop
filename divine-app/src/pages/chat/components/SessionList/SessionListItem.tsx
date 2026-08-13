import { useState } from "react";
import { MessageSquare, Pencil, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import type { Session } from "@/types";
import { formatTime } from "@/utils";

interface SessionListItemProps {
  session: Session;
  active: boolean;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}

export function SessionListItem({
  session,
  active,
  onSelect,
  onRename,
  onDelete,
}: SessionListItemProps) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session.title);

  const commitRename = () => {
    if (title.trim()) {
      onRename(session.id, title.trim());
    }
    setEditing(false);
  };

  const startRename = () => {
    setTitle(session.title);
    setEditing(true);
  };

  return (
    <Flex
      align="center"
      gap={8}
      className={`session-item ${active ? "active" : ""}`}
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
          className="session-rename-input"
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
          <Flex align="center" gap={8} className="session-item-main">
            <MessageSquare size={12} className="session-icon" />
            <div className="session-copy">
              <span className="session-title">{session.title}</span>
              <span className="session-time">{formatTime(session.updated_at)}</span>
            </div>
          </Flex>
          <div className="session-actions">
            <Button
              variant="icon"
              size="small"
              title={t("session.rename", "重命名")}
              aria-label={t("session.rename", "重命名")}
              onClick={(event) => {
                event.stopPropagation();
                startRename();
              }}
            >
              <Pencil size={13} />
            </Button>
            <Button
              variant="icon"
              size="small"
              className="danger"
              title={t("session.delete", "删除")}
              aria-label={t("session.deleteSession", "删除会话")}
              onClick={(event) => {
                event.stopPropagation();
                onDelete(session.id);
              }}
            >
              <Trash2 size={13} />
            </Button>
          </div>
        </>
      )}
    </Flex>
  );
}
