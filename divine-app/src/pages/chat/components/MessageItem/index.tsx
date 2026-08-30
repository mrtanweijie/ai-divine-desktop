import { memo, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeftRight,
  Check,
  ChevronDown,
  Copy,
  Eye,
  FileText,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { DivineAvatar } from "@/components/DivineAvatar";
import { toast } from "@/components/ui/Toast";
import { Flex } from "@/components/ui/Flex";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import { MarkdownView } from "@/pages/chat/components/MarkdownView";
import type { ChatMessage, PreviewFile, TodoItem } from "@/types";
import { copyText, formatSize, formatTime, formatTokens } from "@/utils";
import { ToolStatusCard } from "./ToolStatusCard";
import { SubAgentPanel } from "./SubAgentPanel";
import { groupToolCards } from "./MessageHelpers";

import "./index.less";
interface MessageItemProps {
  message: ChatMessage;
  streaming: boolean;
  sessionId?: string | null;
  username: string;
  workspacePath?: string | null;
  onPreviewFile?: (file: PreviewFile) => void;
  onUserInteract?: () => void;
  /** 本地模型回答上的【重答】：用云端重答同一条问题 */
  onRetryCloud?: (messageId: string) => void;
}

/**
 * 单条消息渲染。React.memo：流式 chunk 更新时只有正在流式的那条消息
 * 的 content 变化（useChatStream 按 id 局部更新），其余历史消息的
 * message 引用不变 → 浅比较跳过整条重渲染（含 MarkdownView 解析、
 * ToolStatusCard、SubAgentPanel 等子树）。
 * 调用方需保证 props 中函数引用稳定（MessageList 已对 onUserInteract
 * 做 useCallback；onPreviewFile/onRetryCloud 来自 index.tsx 的 useCallback）。
 */
export const MessageItem = memo(function MessageItem({
  message,
  streaming,
  sessionId,
  username,
  workspacePath,
  onPreviewFile,
  onUserInteract,
  onRetryCloud,
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
        {!isUser && (message.token_usage || message.content) && (
          <span className="message-meta-hover">
            {message.token_usage && (
              <span
                className="message-token-usage"
                title={
                  message.token_usage.source === "real"
                    ? t(
                        "message.tokenUsageDetail",
                        "输入 {{input}} · 输出 {{output}} · 总计 {{total}} tokens（API 上报）",
                        {
                          input: formatTokens(message.token_usage.input_tokens),
                          output: formatTokens(message.token_usage.output_tokens),
                          total: formatTokens(message.token_usage.total_tokens),
                        }
                      )
                    : t(
                        "message.tokenUsageEstimated",
                        "输入 {{input}} · 输出 {{output}} · 总计 {{total}} tokens（估算）",
                        {
                          input: formatTokens(message.token_usage.input_tokens),
                          output: formatTokens(message.token_usage.output_tokens),
                          total: formatTokens(message.token_usage.total_tokens),
                        }
                      )
                }
              >
                {t("message.tokenTotal", "{{count}} tokens", {
                  value: formatTokens(message.token_usage.total_tokens),
                })}
              </span>
            )}
            {message.content &&
              message.source === "local" &&
              onRetryCloud && (
                <MessageRetryButton
                  onRetry={() => onRetryCloud(message.id)}
                />
              )}
            {message.content && <MessageCopyButton text={message.content} />}
          </span>
        )}
      </Flex>
      {isUser ? (
        <div
          className="user-content"
          onDoubleClick={() => void copyUserContent(message.content, t)}
          title={t("message.doubleClickCopy", "双击复制")}
        >
          <div className="user-text">{message.content}</div>
          {message.preprocess?.organized && (
            <div className="user-preprocess">
              <span className="user-preprocess-badge">
                <Sparkles size={12} />
                {t("message.preprocessOrganized", "已本地整理")}
              </span>
              {message.preprocess.original && (
                <details className="user-preprocess-original">
                  <summary>
                    <ChevronDown size={12} className="user-preprocess-chevron" />
                    {t("message.preprocessShowOriginal", "查看原文")}
                  </summary>
                  <pre>{message.preprocess.original}</pre>
                </details>
              )}
            </div>
          )}
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
          {message.subagents && message.subagents.length > 0 && (
            <SubAgentPanel
              subagents={message.subagents}
              streaming={streaming}
            />
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
            <MarkdownView
              content={message.content}
              streaming={streaming}
              messageId={message.id}
              choiceState={message.choice_state}
            />
          ) : (
            !message.error && (
              <Flex
                className="loading-cursor"
                align="center"
                aria-label={t("message.generating", "正在生成")}
              >
                <LoadingOrb state="shaping" size={20} speed={2} />
                {message.preprocess_pending && (
                  <span className="preprocess-hint">
                    {t(
                      "message.preprocessWorking",
                      "正在本地整理长文本（启动模型/分块整理），请稍候…"
                    )}
                  </span>
                )}
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
});

function MessageCopyButton({ text }: { text: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await copyText(text);
    setCopied(true);
    toast.success(t("message.copied", "内容已复制"));
    setTimeout(() => setCopied(false), 1200);
  };
  return (
    <Button
      variant="icon"
      size="small"
      className="message-copy"
      onClick={(event) => {
        // 点击后主动失焦，避免原生按钮焦点残留
        event.currentTarget.blur();
        void copy();
      }}
      aria-label={t("message.copyContent", "复制内容")}
      title={t("message.copyContent", "复制内容")}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
    </Button>
  );
}

/** 本地模型回答的【重答】：点击用云端重答同一条问题（复制按钮左侧）。 */
function MessageRetryButton({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <Button
      variant="icon"
      size="small"
      className="message-retry"
      onClick={(event) => {
        event.currentTarget.blur();
        onRetry();
      }}
      aria-label={t("message.retryCloud", "用云端重答")}
      title={t("message.retryCloud", "用云端重答")}
    >
      <ArrowLeftRight size={12} />
    </Button>
  );
}

async function copyUserContent(content: string, t: (key: string) => string) {
  if (!content) return;
  await copyText(content);
  toast.success(t("message.copied"));
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
