import { useEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useTranslation } from "react-i18next";
import { MessageItem } from "@/pages/chat/components/MessageItem";
import type { ChatMessage, PreviewFile } from "@/types";
import { EmptyState } from "@/components/ui/EmptyState";
import { ConversationMinimap } from "./ConversationMinimap";

interface MessageTimelineProps {
  messages: ChatMessage[];
  streaming: boolean;
  sessionId?: string | null;
  username: string;
  workspacePath?: string | null;
  onPreviewFile?: (file: PreviewFile) => void;
  hasMoreOlder?: boolean;
  loadingOlder?: boolean;
  onLoadOlder?: () => void;
}

export function MessageList({
  messages,
  streaming,
  sessionId,
  username,
  workspacePath,
  onPreviewFile,
  hasMoreOlder = false,
  loadingOlder = false,
  onLoadOlder,
}: MessageTimelineProps) {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const previousSessionId = useRef<string | null | undefined>(undefined);
  const lastUserMessageId = useRef<string | null>(null);
  const stickToBottom = useRef(true);
  const previousLoadingOlder = useRef(false);
  const olderScrollAnchor = useRef<{
    scrollTop: number;
    height: number;
  } | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 140,
    overscan: 12,
    getItemKey: (index) => messages[index].id,
  });

  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();
  const minimapVisible =
    messages.filter((message) => message.role === "assistant").length > 5;

  const handleScroll = () => {
    const container = scrollRef.current;
    if (!container) return;
    setScrollTop(container.scrollTop);
    setViewportHeight(container.clientHeight);
    const distance =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    stickToBottom.current = distance < 24;
    if (container.scrollTop < 40 && hasMoreOlder && !loadingOlder) {
      onLoadOlder?.();
    }
  };

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const updateViewport = () => {
      setScrollTop(container.scrollTop);
      setViewportHeight(container.clientHeight);
    };
    updateViewport();
    const observer = new ResizeObserver(updateViewport);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const container = scrollRef.current;
    if (loadingOlder && !previousLoadingOlder.current && container) {
      olderScrollAnchor.current = {
        scrollTop: container.scrollTop,
        height: container.scrollHeight,
      };
    }
    if (!loadingOlder && previousLoadingOlder.current && container) {
      const anchor = olderScrollAnchor.current;
      if (anchor) {
        requestAnimationFrame(() => {
          const delta = container.scrollHeight - anchor.height;
          container.scrollTop = anchor.scrollTop + delta;
          olderScrollAnchor.current = null;
        });
      }
    }
    previousLoadingOlder.current = loadingOlder;
  }, [loadingOlder, messages]);

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
    const scrollToBottom = (force = false) => {
      // 在 rAF 回调里按「执行那一刻」的真实位置再校验：
      // 1) stickToBottom 被用户滚动事件置 false 时放弃；
      // 2) 用户已离开底部（哪怕几像素）时不回底——否则流式分片排队的
      //    回底会把触控板/滚轮的每次小步滚动都拽回去（需要滑多次才生效）。
      if (!stickToBottom.current) return;
      const currentDistance =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      if (!force && currentDistance > 4) return;
      container.scrollTop = container.scrollHeight;
    };
    const distance =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (sessionChanged) {
      // 切换会话：强制回到底部
      stickToBottom.current = true;
      requestAnimationFrame(() => scrollToBottom(true));
      requestAnimationFrame(() => scrollToBottom(true));
      return;
    }
    if (userChanged) {
      if (String(lastUser.id).startsWith("local-user-")) {
        // 真正的发送（本地乐观消息）：强制回到底部查看新消息与回复
        stickToBottom.current = true;
        requestAnimationFrame(() => scrollToBottom(true));
        requestAnimationFrame(() => scrollToBottom(true));
      } else {
        // 流结束后服务器恢复导致消息 id 变化：尊重用户位置，不强制拉回
        stickToBottom.current = distance < 200;
        if (stickToBottom.current) {
          requestAnimationFrame(() => scrollToBottom(false));
          requestAnimationFrame(() => scrollToBottom(false));
        }
      }
      return;
    }
    if (!stickToBottom.current) return;
    if (distance < 200) {
      requestAnimationFrame(() => scrollToBottom(false));
    }
  }, [messages, streaming, sessionId]);

  return (
    <div className="message-stage">
      {minimapVisible && (
        <ConversationMinimap
          virtualizer={virtualizer}
          messages={messages}
          scrollTop={scrollTop}
          viewportHeight={viewportHeight}
        />
      )}
      <div className="message-timeline" ref={scrollRef} onScroll={handleScroll}>
        {loadingOlder && (
          <div className="message-loading-older">
            {t("chat.loadingOlder", "加载更早消息...")}
          </div>
        )}
        {messages.length === 0 ? (
          <EmptyState title={t("chat.startNewChat", "开始新的对话")} />
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
                  className={`virtual-message-item${
                    virtualRow.index === 0 ? " first-message" : ""
                  }`}
                  style={{ transform: `translateY(${virtualRow.start}px)` }}
                >
                  <MessageItem
                    message={message}
                    sessionId={sessionId}
                    username={username}
                    workspacePath={workspacePath}
                    onPreviewFile={onPreviewFile}
                    onUserInteract={() => {
                      stickToBottom.current = false;
                    }}
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
    </div>
  );
}
