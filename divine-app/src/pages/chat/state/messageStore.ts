import { useState } from "react";
import type { ChatMessage } from "@/types";

/**
 * 按会话管理的消息与流状态，支持多个对话同时进行：
 * - messagesBySession: 每个会话独立缓存消息列表（含进行中的流式消息）
 * - streamingSessions: 正在生成中的会话 id 集合
 */
export function useMessageState() {
  const [messagesBySession, setMessagesBySession] = useState<
    Record<string, ChatMessage[]>
  >({});
  const [streamingSessions, setStreamingSessions] = useState<Set<string>>(
    () => new Set()
  );

  const setSessionMessages = (
    sessionId: string | null,
    messages: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])
  ) => {
    if (!sessionId) return;
    setMessagesBySession((prev) => {
      const current = prev[sessionId] ?? [];
      const next =
        typeof messages === "function" ? messages(current) : messages;
      return { ...prev, [sessionId]: next };
    });
  };

  const clearSessionMessages = (sessionId: string | null) => {
    if (!sessionId) return;
    setMessagesBySession((prev) => {
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
    setStreamingSessions((prev) => {
      const next = new Set(prev);
      next.delete(sessionId);
      return next;
    });
  };

  const setSessionStreaming = (sessionId: string | null, value: boolean) => {
    if (!sessionId) return;
    setStreamingSessions((prev) => {
      const next = new Set(prev);
      if (value) next.add(sessionId);
      else next.delete(sessionId);
      return next;
    });
  };

  return {
    messagesBySession,
    setSessionMessages,
    clearSessionMessages,
    streamingSessions,
    setSessionStreaming,
  };
}
