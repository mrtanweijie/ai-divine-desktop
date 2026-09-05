import { createContext, useContext } from "react";
import type { ChatFile } from "@/types";

/**
 * 把聊天发送能力提供给消息渲染层的可点击组件（如风格选择卡片）。
 * chat/index.tsx 在 useChatStream 之后注入 sendMessage。
 */
export interface ChatStreamContextValue {
  sendMessage: (question: string, files?: ChatFile[], effort?: string) => void;
  /** 当前输入框的深度思考档位，发送时透传 */
  effort: string;
}

export const ChatStreamContext = createContext<ChatStreamContextValue | null>(null);

export function useChatStreamContext(): ChatStreamContextValue {
  const ctx = useContext(ChatStreamContext);
  if (!ctx) {
    throw new Error("useChatStreamContext must be used within ChatStreamContext.Provider");
  }
  return ctx;
}
