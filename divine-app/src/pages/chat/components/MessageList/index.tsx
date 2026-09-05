import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useTranslation } from "react-i18next";
import { ArrowDown } from "lucide-react";
import { MessageItem } from "@/pages/chat/components/MessageItem";
import type { ChatMessage, PreviewFile } from "@/types";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ConversationMinimap } from "./ConversationMinimap";

import "./index.less";

// B4：倒序找最近一条用户消息的 id（零分配），替代
// `[...messages].reverse().find()` 的每 chunk 整数组拷贝反转。
function findLastUserId(messages: ChatMessage[]): string | undefined {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === "user") return messages[i].id;
  }
  return undefined;
}

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
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  // onScroll 的高频状态提交按帧合并（见 handleScroll 内注释）
  const scrollRafRef = useRef<number | null>(null);

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

  // 稳定引用：MessageItem 是 memo 组件，内联箭头函数会让每次渲染
  // 都生成新引用导致 memo 失效（流式 chunk 更新时所有历史消息白重渲染）。
  const handleUserInteract = useCallback(() => {
    stickToBottom.current = false;
  }, []);

  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();
  // Minimap 显隐：长会话每帧渲染都会到这里，用 useMemo + 计数提前退出
  // 替代每次渲染分配整个过滤数组。
  const minimapVisible = useMemo(() => {
    let assistantCount = 0;
    for (const message of messages) {
      if (message.role === "assistant" && ++assistantCount > 5) return true;
    }
    return false;
  }, [messages]);

  const handleScroll = () => {
    const container = scrollRef.current;
    if (!container) return;
    const newTop = container.scrollTop;
    const distance =
      container.scrollHeight - newTop - container.clientHeight;
    // 用滚动方向判断用户意图（只写 ref，无渲染成本）：
    // - 向上滚动（查看历史）→ 立即解除自动跟随（哪怕只滚了几像素）；
    // - 滚回/位于底部 → 恢复自动跟随。
    if (newTop < lastScrollTopRef.current) {
      stickToBottom.current = false;
    } else if (distance < 4) {
      stickToBottom.current = true;
    }
    lastScrollTopRef.current = newTop;
    if (container.scrollTop < 40 && hasMoreOlder && !loadingOlder) {
      onLoadOlder?.();
    }
    // 滚动事件每帧都会触发（流式自动跟随也在持续改 scrollTop）：
    // rAF 对齐，每帧至多提交一次状态；值未变时函数式 setState 让
    // React 原地跳过，避免每帧 3 个 setState 带动列表 + Minimap
    // 整帧重渲染（长会话下与流式 chunk 重渲染叠乘，是卡顿源之一）。
    if (scrollRafRef.current !== null) return;
    scrollRafRef.current = requestAnimationFrame(() => {
      scrollRafRef.current = null;
      const el = scrollRef.current;
      if (!el) return;
      const top = el.scrollTop;
      setScrollTop((prev) => (prev === top ? prev : top));
      setViewportHeight((prev) =>
        prev === el.clientHeight ? prev : el.clientHeight
      );
      const bottomGap = el.scrollHeight - top - el.clientHeight;
      const showButton = bottomGap > 120;
      setShowScrollToBottom((prev) =>
        prev === showButton ? prev : showButton
      );
    });
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
    return () => {
      observer.disconnect();
      if (scrollRafRef.current !== null) {
        cancelAnimationFrame(scrollRafRef.current);
        scrollRafRef.current = null;
      }
    };
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
    // B4：见模块顶部 findLastUserId 说明
    const lastUserId = findLastUserId(messages);
    const userChanged =
      lastUserId !== undefined && lastUserId !== lastUserMessageId.current;
    if (userChanged) {
      lastUserMessageId.current = lastUserId;
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
      if (String(lastUserId).startsWith("local-user-")) {
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

  const scrollToBottom = useCallback(() => {
    const container = scrollRef.current;
    if (!container) return;
    stickToBottom.current = true;
    lastScrollTopRef.current = -1;
    requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
  }, []);

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
                    onUserInteract={handleUserInteract}
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
      {showScrollToBottom && (
        <Button
          variant="icon"
          className="scroll-to-bottom-btn"
          onClick={scrollToBottom}
          title={t("chat.scrollToBottom", "回到底部")}
          aria-label={t("chat.scrollToBottom", "回到底部")}
        >
          <ArrowDown size={16} />
        </Button>
      )}
    </div>
  );
}
