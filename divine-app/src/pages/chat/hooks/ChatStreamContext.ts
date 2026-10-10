import { createContext, useContext } from "react";
import type { ChatFile } from "@/types";
import type { SurfaceActionInput } from "@/services/api";

/**
 * 面板动作提交的结果。`reason` 只用于给用户一句准确的话（409 该提示
 * "正在生成中"，404 该提示"功能未启用"），不参与控制流 ——
 * 前端不做重试/排队，重试是用户再点一次的语义（§8.2 第 2 条：不排队）。
 */
export type SurfaceSubmitResult =
  { ok: true } | { ok: false; reason: "busy" | "disabled" | "failed" };

export interface SurfaceSubmitOptions {
  /**
   * 回合已被后端受理（2xx，流即将开始）。
   *
   * 与"流跑完"是两回事：面板要用它来**立刻清掉用户编辑态**（§8.3）——
   * 那一刻用户已经"提交"了，新一轮刷新回来的面板才是他该看到的。
   * 等流结束再清就太晚了：新面板挂载时又会被旧编辑态覆盖一遍。
   */
  onAccepted?: () => void;
}

/**
 * 把聊天发送能力提供给消息渲染层的可点击组件（如风格选择卡片、A2UI 面板）。
 * chat/index.tsx 在 useChatStream 之后注入。
 */
export interface ChatStreamContextValue {
  sendMessage: (question: string, files?: ChatFile[], effort?: string) => void;
  /**
   * A2UI 面板动作 → 新回合（design 028 §8）。面板只负责收集
   * 「点了哪个按钮、面板里现在是什么值」，模型档位/审批模式由这里补齐
   * —— 面板不该知道当前用的是哪个模型、要不要深度思考。
   */
  submitSurfaceAction: (
    input: SurfaceActionInput,
    options?: SurfaceSubmitOptions,
  ) => Promise<SurfaceSubmitResult>;
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

/**
 * 宽松版：拿不到 Provider 时返回 `null` 而不是抛错。
 *
 * 面板允许被渲染在没有聊天会话的地方（离线样张、组件测试、历史预览），
 * 那里没有发送能力也不该整块崩掉 —— 此时按钮降级为"点了没反应"而非白屏。
 */
export function useOptionalChatStreamContext(): ChatStreamContextValue | null {
  return useContext(ChatStreamContext);
}
