import { useEffect, useState } from "react";
import {
  ChevronLeft,
  Pencil,
  PanelLeftOpen,
} from "lucide-react";
import type { Session } from "@/types";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";

interface ChatHeaderProps {
  session: Session | null;
  model: string;
  think: boolean;
  onThinkChange: (value: boolean) => void;
  onOpenSidebar: () => void;
  onRename: (id: string, title: string) => void;
}

export function ChatHeader({
  session,
  model,
  think,
  onThinkChange,
  onOpenSidebar,
  onRename,
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
            <span className="session-title-text">{title}</span>
            <Pencil size={13} className="title-pencil" aria-hidden="true" />
          </Button>
        )}
      </Flex>

      <Flex align="center" gap={6} className="chat-header-right">
        <span className="model-badge">{model || "本地演示"}</span>
        <Switch
          label="深度思考"
          checked={think}
          onChange={onThinkChange}
        />
      </Flex>
    </header>
  );
}
