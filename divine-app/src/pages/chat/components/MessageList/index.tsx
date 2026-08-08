import { useEffect, useRef } from "react";
import { MessageItem } from "@/pages/chat/components/MessageItem";
import type { ChatMessage } from "@/types";
import { EmptyState } from "@/components/ui/EmptyState";

interface MessageTimelineProps {
  messages: ChatMessage[];
  streaming: boolean;
  sessionId?: string | null;
  username: string;
}

export function MessageList({
  messages,
  streaming,
  sessionId,
  username,
}: MessageTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const previousSessionId = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const sessionChanged = previousSessionId.current !== sessionId;
    previousSessionId.current = sessionId;
    const scrollToBottom = () => {
      container.scrollTop = container.scrollHeight;
    };
    if (sessionChanged) {
      requestAnimationFrame(scrollToBottom);
      return;
    }
    const distance =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distance < 180 || streaming) {
      requestAnimationFrame(scrollToBottom);
    }
  }, [messages, streaming, sessionId]);

  return (
    <div className="message-timeline" ref={scrollRef}>
      <div className="timeline-inner">
        {messages.length === 0 ? (
          <EmptyState title="开始新的对话" />
        ) : (
          messages.map((message, index) => (
            <MessageItem
              key={message.id}
              message={message}
              username={username}
              streaming={streaming && index === messages.length - 1}
            />
          ))
        )}
      </div>
    </div>
  );
}
