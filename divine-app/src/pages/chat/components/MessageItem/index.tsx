import {
  AlertCircle,
  Check,
  ChevronDown,
  Copy,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  Image,
  Loader2,
  StickyNote,
  Wrench,
} from "lucide-react";
import { useState } from "react";
import { downloadUrl } from "@/services/api";
import { isTauri, openFileLocation } from "@/services/tauri";
import type { ChatMessage, ToolEvent } from "@/types";
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

function ToolStatusCard({ tool }: { tool: ToolEvent }) {
  const [copied, setCopied] = useState(false);
  const running = tool.status === "running" || tool.status === "preparing";
  const statusMessage = tool.status === "done" ? "执行完成" : tool.message;
  const icon =
    tool.tool.includes("spreadsheet") || tool.tool.includes("excel") ? (
      <FileSpreadsheet size={16} />
    ) : tool.tool.includes("notes") ? (
      <StickyNote size={16} />
    ) : tool.tool.includes("read_image") || tool.tool.includes("image") ? (
      <Image size={16} />
    ) : (
      <FileText size={16} />
    );

  const copyJson = async () => {
    if (!tool.result) return;
    await navigator.clipboard.writeText(JSON.stringify(tool.result, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  return (
    <div className={`tool-status-card ${tool.status}`}>
      <Flex align="center" gap={8} className="tool-status-main">
        <span className="tool-icon">
          {running ? <Loader2 size={16} className="spin" /> : <Wrench size={16} />}
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
