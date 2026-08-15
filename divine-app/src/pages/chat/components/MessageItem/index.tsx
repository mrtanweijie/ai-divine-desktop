import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Check,
  ChevronDown,
  Eye,
  FileText,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { DivineAvatar } from "@/components/DivineAvatar";
import { Flex } from "@/components/ui/Flex";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import { MarkdownView } from "@/pages/chat/components/MarkdownView";
import type { ChatMessage, PreviewFile, TodoItem } from "@/types";
import { formatSize, formatTime } from "@/utils";
import { ToolStatusCard } from "./ToolStatusCard";
import { groupToolCards } from "./MessageHelpers";

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
              thinking={message.thinking}
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
  thinking,
  onUserInteract,
}: {
  content: string;
  thinking?: boolean;
  onUserInteract?: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const latestLine = lines[lines.length - 1] ?? "";
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
        <span className="think-title">
          {t("message.thinking", "思考过程")}
        </span>
        {!open && thinking && latestLine && (
          <span className="think-preview" title={latestLine}>
            {latestLine}
          </span>
        )}
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
