import { useEffect, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { MessageItem } from "@/pages/chat/components/MessageItem";
import type { ChatMessage, PreviewFile } from "@/types";
import { EmptyState } from "@/components/ui/EmptyState";

interface MessageTimelineProps {
  messages: ChatMessage[];
  streaming: boolean;
  sessionId?: string | null;
  username: string;
  workspacePath?: string | null;
  onPreviewFile?: (file: PreviewFile) => void;
}

export function MessageList({
  messages,
  streaming,
  sessionId,
  username,
  workspacePath,
  onPreviewFile,
}: MessageTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const previousSessionId = useRef<string | null | undefined>(undefined);
  const lastUserMessageId = useRef<string | null>(null);
  const stickToBottom = useRef(true);

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 140,
    overscan: 12,
    getItemKey: (index) => messages[index].id,
  });

  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  const handleScroll = () => {
    const container = scrollRef.current;
    if (!container) return;
    const distance =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    stickToBottom.current = distance < 80;
  };

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const sessionChanged = previousSessionId.current !== sessionId;
    previousSessionId.current = sessionId;
    const lastUser = [...messages].reverse().find(
      (message) => message.role === "user"
    );
    const userChanged =
      lastUser !== undefined && lastUser.id !== lastUserMessageId.current;
    if (userChanged) {
      lastUserMessageId.current = lastUser.id;
    }
    const scrollToBottom = () => {
      container.scrollTop = container.scrollHeight;
    };
    if (sessionChanged || userChanged) {
      stickToBottom.current = true;
      requestAnimationFrame(scrollToBottom);
      requestAnimationFrame(scrollToBottom);
      return;
    }
    if (!stickToBottom.current) return;
    const distance =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distance < 200) {
      requestAnimationFrame(scrollToBottom);
    }
  }, [messages, streaming, sessionId]);

  return (
    <div className="message-timeline" ref={scrollRef} onScroll={handleScroll}>
      {messages.length === 0 ? (
        <EmptyState title="开始新的对话" />
      ) : (
        <div
          className="timeline-inner"
          style={{ height: totalSize, position: "relative" }}
        >
          {virtualItems.map((virtualRow) => {
            const message = messages[virtualRow.index];
            return (
              <div
                key={message.id}
                data-index={virtualRow.index}
                ref={virtualizer.measureElement}
                className="virtual-message-item"
                style={{ transform: `translateY(${virtualRow.start}px)` }}
              >
                <MessageItem
                  message={message}
                  username={username}
                  workspacePath={workspacePath}
                  onPreviewFile={onPreviewFile}
                  streaming={
                    streaming && virtualRow.index === messages.length - 1
                  }
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
