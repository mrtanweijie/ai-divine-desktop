import { useEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useTranslation } from "react-i18next";
import { MessageItem } from "@/pages/chat/components/MessageItem";
import type { ChatMessage, PreviewFile } from "@/types";
import { EmptyState } from "@/components/ui/EmptyState";
import { ConversationMinimap } from "./ConversationMinimap";

import "./index.less";
interface MessageTimelineProps {
  messages: ChatMessage[];
  streaming: boolean;
  sessionId?: string | null;
  username: string;
  workspacePath?: string | null;
  onPreviewFile?: (file: PreviewFile) => void;
  onRetryCloud?: (messageId: string) => void;
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
  onRetryCloud,
  hasMoreOlder = false,
  loadingOlder = false,
  onLoadOlder,
}: MessageTimelineProps) {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const previousSessionId = useRef<string | null | undefined>(undefined);
  const lastUserMessageId = useRef<string | null>(null);
  const stickToBottom = useRef(true);
  const lastScrollTopRef = useRef(0);
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
    // 默认 useFlushSync=true，measureElement 的 ref 绑定在 layout effect
    // commit 阶段触发 onChange → flushSync → React 报错
    // "flushSync was called from inside a lifecycle method"
    // 关闭后用普通 rerender()，避免在 React commit 期间同步刷新。
    useFlushSync: false,
  });

  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();
  const minimapVisible =
    messages.filter((message) => message.role === "assistant").length > 5;

  const handleScroll = () => {
    const container = scrollRef.current;
    if (!container) return;
    const newTop = container.scrollTop;
    const distance =
      container.scrollHeight - newTop - container.clientHeight;
    // 用滚动方向判断用户意图：
    // - 向上滚动（查看历史）→ 立即解除自动跟随（哪怕只滚了几像素）；
    // - 滚回/位于底部 → 恢复自动跟随。
    if (newTop < lastScrollTopRef.current) {
      stickToBottom.current = false;
    } else if (distance < 4) {
      stickToBottom.current = true;
    }
    lastScrollTopRef.current = newTop;
    setScrollTop(newTop);
    setViewportHeight(container.clientHeight);
    if (container.scrollTop < 40 && hasMoreOlder && !loadingOlder) {
      onLoadOlder?.();
    }
  };

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    lastScrollTopRef.current = container.scrollTop;
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
    const scrollToBottom = () => {
      // 只信任 stickToBottom（由滚动方向维护的用户意图）：
      // 在底部时内容增长会让「距离」变大，不能再按距离判断，
      // 否则会同时掐死正常的流式跟随。
      if (!stickToBottom.current) return;
      container.scrollTop = container.scrollHeight;
    };
    const distance =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (sessionChanged) {
      // 切换会话：强制回到底部
      stickToBottom.current = true;
      // 重置方向哨兵，避免程序化回底被误判为「向上滚动」而解除跟随
      lastScrollTopRef.current = -1;
      requestAnimationFrame(scrollToBottom);
      requestAnimationFrame(scrollToBottom);
      return;
    }
    if (userChanged) {
      if (String(lastUser.id).startsWith("local-user-")) {
        // 真正的发送（本地乐观消息）：强制回到底部查看新消息与回复
        stickToBottom.current = true;
        lastScrollTopRef.current = -1;
        requestAnimationFrame(scrollToBottom);
        requestAnimationFrame(scrollToBottom);
      } else {
        // 流结束后服务器恢复导致消息 id 变化：尊重用户位置，不强制拉回
        stickToBottom.current = distance < 200;
        if (stickToBottom.current) {
          requestAnimationFrame(scrollToBottom);
          requestAnimationFrame(scrollToBottom);
        }
      }
      return;
    }
    // 自动跟随：stickToBottom 为 true 时跟随流式输出（滚动方向负责解除）
    if (!stickToBottom.current) return;
    requestAnimationFrame(scrollToBottom);
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
                    onRetryCloud={onRetryCloud}
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
