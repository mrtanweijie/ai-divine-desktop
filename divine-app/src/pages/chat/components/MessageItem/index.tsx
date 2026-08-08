import {
  AlertCircle,
  Calculator,
  Check,
  ChevronDown,
  Copy,
  Database,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  FolderTree,
  Globe,
  Image,
  ListChecks,
  Presentation,
  StickyNote,
  TerminalSquare,
  Wrench,
} from "lucide-react";
import { useState } from "react";
import { apiBase, downloadUrl } from "@/services/api";
import { isTauri, openFileLocation } from "@/services/tauri";
import type { ChatMessage, TodoItem, ToolEvent } from "@/types";
import { formatSize, formatTime } from "@/utils";
import { MarkdownView } from "@/pages/chat/components/MarkdownView";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { LoadingOrb } from "@/components/ui/LoadingOrb";

interface MessageItemProps {
  message: ChatMessage;
  streaming: boolean;
  username: string;
}

export function MessageItem({
  message,
  streaming,
  username,
}: MessageItemProps) {
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
          <span className="divine-avatar" aria-hidden="true">
            <svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M8 2.5 L14 13.5 H2 Z"
                fill="none"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        )}
        <span className="role-label">
          {isUser ? username || "用户" : "Divine"}
        </span>
        <time className="message-time">{formatTime(message.created_at)}</time>
      </Flex>
      {isUser ? (
        <div className="user-content">
          <div className="user-text">{message.content}</div>
          {message.files && message.files.length > 0 && (
            <div className="user-files">
              {message.files.map((file) => (
                <div className="user-file-card" key={file.name}>
                  <FileText size={13} />
                  <span>{file.name}</span>
                  {file.size != null && (
                    <span className="user-file-size">
                      {formatSize(file.size)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="assistant-content">
          {message.think && <ThinkBlock content={message.think} />}
          {message.todos && message.todos.length > 0 && (
            <PlanCard todos={message.todos} />
          )}
          {message.tools.map((tool, index) => (
            <ToolStatusCard key={`${tool.tool}-${index}`} tool={tool} />
          ))}
          {message.content ? (
            <MarkdownView content={message.content} streaming={streaming} />
          ) : (
            !message.error && (
              <Flex className="loading-cursor" aria-label="正在生成">
                <LoadingOrb state="shaping" size={20} speed={2} />
              </Flex>
            )
          )}
          {streaming && message.content && (
            <span className="stream-orb">
              <LoadingOrb state="connecting" size={20} speed={2} />
              <span className="stream-text">Working...</span>
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

function ThinkBlock({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="think-block" open={open}>
      <summary
        className="think-summary"
        onClick={(event) => {
          event.preventDefault();
          setOpen((value) => !value);
        }}
      >
        <ChevronDown size={13} className={open ? "expanded" : ""} />
        <span>思考过程</span>
      </summary>
      <div className="think-content">{content}</div>
    </details>
  );
}

function PlanCard({ todos }: { todos: TodoItem[] }) {
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
        <span>执行计划</span>
        <span className="plan-progress">
          {done}/{todos.length}
        </span>
      </summary>
      <div className="plan-items">
        {todos.map((todo) => (
          <div key={todo.id} className={`plan-item ${todo.status}`}>
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

function ToolStatusCard({ tool }: { tool: ToolEvent }) {
  const [copied, setCopied] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const running = tool.status === "running" || tool.status === "preparing";
  const statusMessage = tool.status === "done" ? "执行完成" : tool.message;
  const icon =
    tool.tool.includes("spreadsheet") || tool.tool.includes("excel") ? (
      <FileSpreadsheet size={16} />
    ) : tool.tool.includes("notes") ? (
      <StickyNote size={16} />
    ) : tool.tool.includes("read_image") || tool.tool.includes("image") ? (
      <Image size={16} />
    ) : tool.tool.includes("calculator") ? (
      <Calculator size={16} />
    ) : tool.tool.includes("clipboard") ? (
      <Copy size={16} />
    ) : tool.tool.includes("sqlite") || tool.tool.includes("database") ? (
      <Database size={16} />
    ) : tool.tool.includes("directory") || tool.tool.includes("tree") ? (
      <FolderTree size={16} />
    ) : tool.tool.includes("presentation") ||
      tool.tool.includes("ppt") ||
      tool.tool.includes("slides") ? (
      <Presentation size={16} />
    ) : tool.tool.includes("web") ||
      tool.tool.includes("fetch") ||
      tool.tool.includes("browse") ||
      tool.tool.includes("url") ? (
      <Globe size={16} />
    ) : tool.tool === "terminal" ? (
      <TerminalSquare size={16} />
    ) : (
      <FileText size={16} />
    );

  const copyJson = async () => {
    if (!tool.result) return;
    await navigator.clipboard.writeText(JSON.stringify(tool.result, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  const decide = async (allow: boolean) => {
    if (!tool.session_id || deciding) return;
    setDeciding(true);
    try {
      await fetch(`${apiBase()}/terminal/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: tool.session_id, allow }),
      });
    } finally {
      setDeciding(false);
    }
  };

  return (
    <div className={`tool-status-card ${tool.status}`}>
      <Flex align="center" gap={8} className="tool-status-main">
        <span className="tool-icon">
          {running ? (
            <LoadingOrb state="solving" size={20} speed={3} />
          ) : (
            <Wrench size={16} />
          )}
        </span>
        <div className="tool-copy">
          <span className="tool-name">{tool.tool}</span>
          <span className="tool-message">{statusMessage}</span>
        </div>
      </Flex>
      {tool.status === "done" && tool.result?.filepath && (
        <a
          className="file-download"
          href={
            tool.result.download_url
              ? downloadUrl(tool.result.download_url)
              : "#"
          }
          target="_blank"
          rel="noreferrer"
          title="打开所在目录"
          onClick={(event) => {
            if (tool.result?.filepath && isTauri()) {
              event.preventDefault();
              void openFileLocation(tool.result.filepath);
            }
          }}
        >
          <FolderOpen size={14} />
          <span>{tool.result.file_name}</span>
          <span className="file-size">{formatSize(tool.result.file_size)}</span>
        </a>
      )}
      {tool.command && tool.status !== "confirm" && (
        <div className="terminal-command">
          <span className="terminal-command-prompt">$</span>
          <code>{tool.command}</code>
        </div>
      )}
      {tool.status === "confirm" &&
        tool.confirm_type !== "external_file" &&
        tool.command && (
        <div className="terminal-confirm">
          <div className="terminal-confirm-head">
            <TerminalSquare size={14} />
            <span>终端命令确认</span>
          </div>
          <pre>{tool.command}</pre>
          <Flex align="center" gap={8}>
            <Button size="small" loading={deciding} onClick={() => void decide(true)}>
              允许执行
            </Button>
            <Button
              size="small"
              variant="ghost"
              disabled={deciding}
              onClick={() => void decide(false)}
            >
              拒绝
            </Button>
          </Flex>
        </div>
      )}
      {tool.status === "confirm" && tool.confirm_type === "external_file" && (
        <div className="terminal-confirm external-file-confirm">
          <div className="terminal-confirm-head">
            <FolderOpen size={14} />
            <span>外部文件访问确认</span>
          </div>
          <pre>{(tool.paths ?? [tool.command]).join("\n")}</pre>
          <Flex align="center" gap={8}>
            <Button size="small" loading={deciding} onClick={() => void decide(true)}>
              允许访问
            </Button>
            <Button
              size="small"
              variant="ghost"
              disabled={deciding}
              onClick={() => void decide(false)}
            >
              拒绝
            </Button>
          </Flex>
        </div>
      )}
      {tool.status === "confirm" && tool.confirm_type === "plan" && (
        <div className="terminal-confirm plan-confirm">
          <div className="terminal-confirm-head">
            <ListChecks size={14} />
            <span>执行计划确认</span>
          </div>
          <p className="plan-confirm-text">计划已创建，是否开始执行？</p>
          <Flex align="center" gap={8}>
            <Button size="small" loading={deciding} onClick={() => void decide(true)}>
              开始执行
            </Button>
            <Button
              size="small"
              variant="ghost"
              disabled={deciding}
              onClick={() => void decide(false)}
            >
              取消
            </Button>
          </Flex>
        </div>
      )}
      {running && (
        <div className="tool-progress" aria-hidden="true">
          <span className="tool-progress-bar" />
        </div>
      )}
      {tool.status === "done" && tool.result && (
        <Flex align="center" gap={8} className="tool-result-actions">
          {icon}
          <span>{tool.result.message}</span>
          <Button
            variant="icon"
            size="small"
            onClick={copyJson}
            title="复制结果"
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </Button>
        </Flex>
      )}
    </div>
  );
}
