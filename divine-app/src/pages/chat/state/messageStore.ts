import { useState } from "react";
import type { ChatMessage } from "@/types";

export function useMessageState() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);

  return { messages, setMessages, streaming, setStreaming };
}
