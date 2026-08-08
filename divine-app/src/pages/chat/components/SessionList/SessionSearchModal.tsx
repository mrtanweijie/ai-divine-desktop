import { useMemo, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import type { Session } from "@/types";
import "./SessionSearchModal.less";

interface SessionSearchModalProps {
  open: boolean;
  sessions: Session[];
  selectedId: string | null;
  onClose: () => void;
  onSelect: (id: string) => void;
}

export function SessionSearchModal({
  open,
  sessions,
  selectedId,
  onClose,
  onSelect,
}: SessionSearchModalProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!text) return sessions;
    return sessions.filter((session) =>
      session.title.toLowerCase().includes(text)
    );
  }, [query, sessions]);

  return (
    <Modal open={open} title="搜索会话" onClose={onClose} width={420}>
      <Input
        autoFocus
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="输入会话标题…"
        aria-label="搜索会话"
      />
      <div className="session-search-results">
        {filtered.length === 0 ? (
          <EmptyState title="没有匹配的会话" />
        ) : (
          filtered.map((session) => (
            <button
              key={session.id}
              type="button"
              className={`session-search-result${
                session.id === selectedId ? " active" : ""
              }`}
              onClick={() => {
                onSelect(session.id);
                onClose();
              }}
            >
              <span className="session-search-title">{session.title}</span>
            </button>
          ))
        )}
      </div>
    </Modal>
  );
}
