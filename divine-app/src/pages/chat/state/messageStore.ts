import { useCallback, useRef, useState } from "react";
import type { ChatMessage } from "@/types";

/**
 * 按会话管理的消息与流状态，支持多个对话同时进行：
 * - messagesBySession: 每个会话独立缓存消息列表（含进行中的流式消息）
 * - streamingSessions: 正在生成中的会话 id 集合
 *
 * 所有辅助函数均 useCallback 稳定，避免把 state 对象放进依赖数组导致
 * 组件/effect 在每次消息更新时级联重建。
 */
export function useMessageState() {
  const [messagesBySession, setMessagesBySession] = useState<Record<string, ChatMessage[]>>({});
  const messagesBySessionRef = useRef<Record<string, ChatMessage[]>>({});
  const [streamingSessions, setStreamingSessions] = useState<Set<string>>(() => new Set());

  const setSessionMessages = useCallback(
    (
      sessionId: string | null,
      messages: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[]),
    ) => {
      if (!sessionId) return;
      setMessagesBySession((prev) => {
        const current = prev[sessionId] ?? [];
        const next = typeof messages === "function" ? messages(current) : messages;
        const updated = { ...prev, [sessionId]: next };
        messagesBySessionRef.current = updated;
        return updated;
      });
    },
    [],
  );

  const clearSessionMessages = useCallback((sessionId: string | null) => {
    if (!sessionId) return;
    setMessagesBySession((prev) => {
      const next = { ...prev };
      delete next[sessionId];
      messagesBySessionRef.current = next;
      return next;
    });
    setStreamingSessions((prev) => {
      const next = new Set(prev);
      next.delete(sessionId);
      return next;
    });
  }, []);

  const setSessionStreaming = useCallback((sessionId: string | null, value: boolean) => {
    if (!sessionId) return;
    setStreamingSessions((prev) => {
      const next = new Set(prev);
      if (value) next.add(sessionId);
      else next.delete(sessionId);
      return next;
    });
  }, []);

  // 读取某会话的缓存消息（走 ref，稳定引用；不把 state 放进依赖数组）
  const getCachedSessionMessages = useCallback((sessionId: string | null) => {
    if (!sessionId) return undefined;
    return messagesBySessionRef.current[sessionId];
  }, []);

  return {
    messagesBySession,
    setSessionMessages,
    clearSessionMessages,
    streamingSessions,
    setSessionStreaming,
    getCachedSessionMessages,
  };
}
