import { useEffect, useRef } from "react";
import { MessageItem } from "@/pages/chat/components/MessageItem";
import type { ChatMessage } from "@/types";
import { EmptyState } from "@/components/ui/EmptyState";

interface MessageTimelineProps {
  messages: ChatMessage[];
  streaming: boolean;
}

export function MessageList({ messages, streaming }: MessageTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const distance =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distance < 180 || streaming) {
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    }
  }, [messages, streaming]);

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
              streaming={streaming && index === messages.length - 1}
            />
          ))
        )}
      </div>
    </div>
  );
}
