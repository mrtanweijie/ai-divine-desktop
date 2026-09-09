// Owns the POST /stream_chat SSE flow for a chat page instance.
import { useCallback, useRef } from "react";
import type { Dispatch, MutableRefObject, SetStateAction } from "react";
import type { TFunction } from "i18next";
import i18next from "@/i18n";
import {
  cancelSessionGeneration,
  createSession,
  getSession,
  injectSupplement,
  messagesToChatMessages,
} from "@/services/api";
import { requestRaw } from "@/services/request";
import { consumeSSE } from "@/services/sse";
import { readThemePreference, resolveTheme } from "@/services/theme";
import { createStreamBuffer } from "@/pages/chat/hooks/streamBuffer";
import { setSessionEffort } from "@/pages/chat/state/sessionEffort";
import { setSessionModelId } from "@/pages/chat/state/sessionModel";
import { emitEventsChanged, emitTasksChanged } from "@/services/scheduledTasks";
import {
  changedFilePathsFromResult,
  changedFileRel,
  mergeLocalTools,
  SUPPLEMENT_PREFIX,
  upsertSubAgent,
  upsertTool,
} from "@/pages/chat/chatUtils";
import type {
  ApprovalMode,
  ChatFile,
  ChatMessage,
  Project,
  Session,
  SubAgentItem,
  TodoItem,
  ToolEvent,
} from "@/types";

interface UseChatStreamOptions {
  selectedId: string | null;
  selectedProjectId: string | null;
  projects: Project[];
  approvalMode: ApprovalMode;
  streaming: boolean;
  modelId: string | null;
  workspacePanelOpenRef: MutableRefObject<boolean>;
  setSessions: Dispatch<SetStateAction<Session[]>>;
  setSelectedId: (id: string | null) => void;
  setSessionMessages: (
    sessionId: string | null,
    messages: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[]),
  ) => void;
  setSessionStreaming: (sessionId: string | null, value: boolean) => void;
  setAgentChangedFiles: Dispatch<SetStateAction<Set<string>>>;
  setHasMoreOlder: Dispatch<SetStateAction<boolean>>;
  setOldestMessageId: Dispatch<SetStateAction<string | null>>;
  refreshSessions: (projectId?: string | null) => Promise<Session[]>;
  refreshProjects: () => Promise<Project[]>;
  refreshWorkspace: () => Promise<void>;
  loadChangedFiles: (id: string) => Promise<void>;
  t: TFunction;
}

export function useChatStream(options: UseChatStreamOptions) {
  const {
    selectedId,
    selectedProjectId,
    projects,
    approvalMode,
    streaming,
    modelId,
    workspacePanelOpenRef,
    setSessions,
    setSelectedId,
    setSessionMessages,
    setSessionStreaming,
    setAgentChangedFiles,
    setHasMoreOlder,
    setOldestMessageId,
    refreshSessions,
    refreshProjects,
    refreshWorkspace,
    loadChangedFiles,
    t,
  } = options;

  // 各会话正在进行的流的 AbortController（多会话并发时按会话区分）；
  // 停止时中止对应会话的连接实现即时反馈。
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());

  // 流式事件处理器（sendMessage / retryCloud 共用）：把事件写进
  // assistantId 对应的乐观消息，done 时从服务端恢复整段会话。
  // 返回 buffer 供调用方在中断/收尾时 flush/dispose。
  const buildStreamHandlers = useCallback(
    (sessionId: string, assistantId: string) => {
      // B2：文本增量先进缓冲区，rAF 帧对齐合并成一次 setSessionMessages，
      // 渲染频率从每 chunk 一次降到 ≤60Hz；think 与 content 同帧一次提交。
      const buffer = createStreamBuffer(({ think, content }) => {
        setSessionMessages(sessionId, (prev) =>
          prev.map((message) => {
            if (message.id !== assistantId) return message;
            const next: ChatMessage = { ...message };
            if (think) {
              next.think = (message.think ?? "") + think;
              next.thinking = true;
            }
            if (content) {
              next.content = message.content + content;
              next.thinking = false;
              next.preprocess_pending = false;
            }
            return next;
          }),
        );
      });

      const handlers = {
        think: ({ content }: { content: string }) => {
          buffer.pushThink(content);
        },
        think_done: () => {
          // 先把缓冲里的思考文本落上屏，再收起「思考中」指示
          buffer.flush();
          setSessionMessages(sessionId, (prev) =>
            prev.map((message) =>
              message.id === assistantId ? { ...message, thinking: false } : message,
            ),
          );
        },
        message: ({ content }: { content: string }) => {
          buffer.pushContent(content);
        },
        plan: (data: { items?: unknown }) => {
          const items = (data.items ?? []) as unknown as TodoItem[];
          setSessionMessages(sessionId, (prev) =>
            prev.map((message) =>
              message.id === assistantId ? { ...message, todos: items } : message,
            ),
          );
        },
        plan_sync: (data: { items?: unknown }) => {
          // run 正常结束后的终态收敛全量同步（running→done、pending→skipped），
          // 保证流式期间与刷新后的计划进度一致。
          const items = (data.items ?? []) as unknown as TodoItem[];
          setSessionMessages(sessionId, (prev) =>
            prev.map((message) =>
              message.id === assistantId ? { ...message, todos: items } : message,
            ),
          );
        },
        todo_update: (data: { id: string; status: string; result?: string }) => {
          const next = data as {
            id: string;
            status: TodoItem["status"];
            result?: string;
          };
          setSessionMessages(sessionId, (prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    todos: (message.todos ?? []).map((todo) =>
                      todo.id === next.id
                        ? { ...todo, status: next.status, result: next.result }
                        : todo,
                    ),
                  }
                : message,
            ),
          );
        },
        tool: (data: unknown) => {
          const event = data as unknown as ToolEvent;
          const added: string[] = [];
          if (event.status === "done" && event.result) {
            const projectPath = projects.find((item) => item.id === selectedProjectId)?.path;
            if (projectPath) {
              for (const filePath of changedFilePathsFromResult(event.result)) {
                const rel = changedFileRel(projectPath, filePath);
                if (rel && workspacePanelOpenRef.current) {
                  added.push(rel);
                }
              }
            }
          }
          // B3：预整理清除与工具卡更新合并进同一次 prev.map()，
          // 避免每个工具事件触发两次全量数组重建。
          setSessionMessages(sessionId, (prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    preprocess_pending: false,
                    tools: upsertTool(message.tools, event),
                  }
                : message,
            ),
          );
          if (added.length) {
            setAgentChangedFiles((prev) => {
              const next = new Set(prev);
              for (const rel of added) next.add(rel);
              return next;
            });
          }
        },
        subagent: (data: unknown) => {
          const raw = data as {
            sub_id: string;
            name: string;
            status: SubAgentItem["status"];
            summary: string;
            error?: string;
          };
          const item: SubAgentItem = {
            id: raw.sub_id,
            name: raw.name,
            status: raw.status,
            summary: raw.summary,
            error: raw.error,
          };
          setSessionMessages(sessionId, (prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    subagents: upsertSubAgent(message.subagents ?? [], item),
                  }
                : message,
            ),
          );
        },
        scheduled_tasks_changed: () => {
          emitTasksChanged();
        },
        calendar_events_changed: () => {
          emitEventsChanged();
        },
        done: async () => {
          buffer.flush();
          setSessionMessages(sessionId, (prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    streaming: false,
                    thinking: false,
                    preprocess_pending: false,
                  }
                : message,
            ),
          );
          if (sessionId) {
            const data = await getSession(sessionId);
            const restored = messagesToChatMessages(
              data.messages,
              data.tool_runs ?? [],
              data.todos,
            );
            setSessionMessages(sessionId, (prev) => mergeLocalTools(prev, restored));
            setHasMoreOlder(false);
            setOldestMessageId(null);
          }
          // B5：侧边栏/工作区元数据刷新不阻塞流结束的视觉收尾，错峰执行
          setTimeout(() => {
            void Promise.all([
              refreshSessions(selectedProjectId),
              refreshProjects(),
              refreshWorkspace(),
            ]).catch(() => undefined);
            if (sessionId && workspacePanelOpenRef.current) {
              void loadChangedFiles(sessionId).catch(() => undefined);
            }
          }, 0);
        },
        error: ({
          message,
          messageKey,
          messageParams,
        }: {
          message: string;
          messageKey?: string;
          messageParams?: Record<string, unknown>;
        }) => {
          buffer.flush();
          setSessionMessages(sessionId, (prev) =>
            prev.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    streaming: false,
                    thinking: false,
                    error: messageKey
                      ? t(messageKey, {
                          ...(messageParams ?? {}),
                          defaultValue: message,
                        })
                      : message,
                  }
                : item,
            ),
          );
        },
      };

      return { buffer, handlers };
    },
    [
      loadChangedFiles,
      projects,
      workspacePanelOpenRef,
      refreshProjects,
      refreshSessions,
      refreshWorkspace,
      selectedProjectId,
      setAgentChangedFiles,
      setHasMoreOlder,
      setOldestMessageId,
      setSessionMessages,
      t,
    ],
  );

  const sendMessage = useCallback(
    async (question: string, files: ChatFile[], effort: string) => {
      // "off" disables deep thinking; any other value enables it at that
      // reasoning effort level.
      const think = effort !== "off";
      // Optimistically append user/assistant messages, then stream SSE events
      // into the assistant message and finally restore server-persisted state.
      const trimmed = question.trim();
      if ((!trimmed && files.length === 0) || streaming) return;
      const effectiveQuestion = trimmed || t("chat.analyzeAttachment", "请分析附件");
      let sessionId = selectedId;
      if (!sessionId) {
        const projectId = selectedProjectId ?? projects[0]?.id ?? null;
        if (!projectId) return;
        const session = await createSession(
          undefined,
          projectId,
          approvalMode,
          i18next.language || "zh-CN",
        );
        sessionId = session.id;
        setSessions((prev) => [session, ...prev]);
        setSelectedId(session.id);
        // 新会话首次发送即记住本条消息使用的深度思考档位与模型。
        setSessionEffort(session.id, effort);
        if (modelId) setSessionModelId(session.id, modelId);
      }

      const userMessage: ChatMessage = {
        id: `local-user-${Date.now()}`,
        role: "user",
        content: effectiveQuestion,
        created_at: new Date().toISOString(),
        tools: [],
        files,
      };
      // 预整理判定（与服务端触发规则一致的前端近似）：整理指令词 / 长文本 /
      // 大附件 → 等待期间显示"正在本地整理"过程反馈
      const expectsPreprocess =
        trimmed.length > 800 ||
        /整理|梳理|归纳|总结/.test(trimmed) ||
        files.some((f) => (f.size ?? 0) >= 20000);
      const assistantMessage: ChatMessage = {
        id: `local-assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
        tools: [],
        streaming: true,
        preprocess_pending: expectsPreprocess,
      };
      setSessionMessages(sessionId, (prev) => [...prev, userMessage, assistantMessage]);
      setSessionStreaming(sessionId, true);

      // 支持立即停止：中止 SSE 连接（前端即时反应）+ 后端取消接口善后
      const controller = new AbortController();
      abortControllersRef.current.set(sessionId, controller);
      const { buffer, handlers } = buildStreamHandlers(sessionId, assistantMessage.id);
      try {
        const response = await requestRaw("/stream_chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({
            question: effectiveQuestion,
            session_id: sessionId,
            approval_mode: approvalMode,
            think,
            ...(think ? { reasoning_effort: effort } : {}),
            ...(modelId ? { model_id: modelId } : {}),
            locale: i18next.language || "zh-CN",
            // 传 resolved 值（dark/light），不传 preference——后端不认 "system"
            ui_theme: resolveTheme(readThemePreference()),
            attachments: files.map((file) => ({
              name: file.name,
              size: file.size,
              ...(file.path ? { file_path: file.path } : { content: file.content ?? "" }),
            })),
          }),
        });
        await consumeSSE(response, handlers);
      } catch (error) {
        // 中断/网络错误时先把缓冲区里的增量落上屏，避免丢尾字
        buffer.flush();
        if (controller.signal.aborted) {
          // 主动点击停止：中止连接，不显示错误，只结束流式态
          setSessionMessages(sessionId, (prev) =>
            prev.map((item) =>
              item.id === assistantMessage.id
                ? { ...item, streaming: false, thinking: false }
                : item,
            ),
          );
        } else {
          setSessionMessages(sessionId, (prev) =>
            prev.map((item) =>
              item.id === assistantMessage.id
                ? {
                    ...item,
                    streaming: false,
                    thinking: false,
                    error:
                      error instanceof Error
                        ? error.message
                        : t("chat.requestFailed", "请求失败，请稍后重试"),
                  }
                : item,
            ),
          );
        }
      } finally {
        // 多会话并发：每个流的收尾只清理它自己的会话标记，
        // 与其它会话是否在流式无关。
        buffer.dispose();
        if (abortControllersRef.current.get(sessionId) === controller) {
          abortControllersRef.current.delete(sessionId);
        }
        setSessionStreaming(sessionId, false);
      }
    },
    [
      approvalMode,
      buildStreamHandlers,
      modelId,
      projects,
      selectedId,
      selectedProjectId,
      setSelectedId,
      setSessionMessages,
      setSessions,
      setSessionStreaming,
      streaming,
      t,
    ],
  );

  // 本地模型回答不满意 → 用云端重答同一条问题（POST /chat/retry_cloud）。
  // 与 sendMessage 不同：不复述用户消息，只追加一条云端回答的乐观气泡。
  const retryCloud = useCallback(
    async (messageId: string, effort: string) => {
      const sessionId = selectedId;
      if (!sessionId || streaming) return;
      const think = effort !== "off";
      const assistantMessage: ChatMessage = {
        id: `retry-assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
        tools: [],
        streaming: true,
      };
      setSessionMessages(sessionId, (prev) => [...prev, assistantMessage]);
      setSessionStreaming(sessionId, true);

      const controller = new AbortController();
      abortControllersRef.current.set(sessionId, controller);
      const { buffer, handlers } = buildStreamHandlers(sessionId, assistantMessage.id);
      try {
        const response = await requestRaw("/chat/retry_cloud", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({
            session_id: sessionId,
            message_id: messageId,
            approval_mode: approvalMode,
            think,
            ...(think ? { reasoning_effort: effort } : {}),
            ...(modelId ? { model_id: modelId } : {}),
            locale: i18next.language || "zh-CN",
            // 传 resolved 值（dark/light），不传 preference——后端不认 "system"
            ui_theme: resolveTheme(readThemePreference()),
          }),
        });
        await consumeSSE(response, handlers);
      } catch (error) {
        // 中断/网络错误时先把缓冲区里的增量落上屏，避免丢尾字
        buffer.flush();
        if (controller.signal.aborted) {
          setSessionMessages(sessionId, (prev) =>
            prev.map((item) =>
              item.id === assistantMessage.id
                ? { ...item, streaming: false, thinking: false }
                : item,
            ),
          );
        } else {
          setSessionMessages(sessionId, (prev) =>
            prev.map((item) =>
              item.id === assistantMessage.id
                ? {
                    ...item,
                    streaming: false,
                    thinking: false,
                    error:
                      error instanceof Error
                        ? error.message
                        : t("chat.requestFailed", "请求失败，请稍后重试"),
                  }
                : item,
            ),
          );
        }
      } finally {
        buffer.dispose();
        if (abortControllersRef.current.get(sessionId) === controller) {
          abortControllersRef.current.delete(sessionId);
        }
        setSessionStreaming(sessionId, false);
      }
    },
    [
      approvalMode,
      buildStreamHandlers,
      modelId,
      selectedId,
      setSessionMessages,
      setSessionStreaming,
      streaming,
      t,
    ],
  );

  // 立即停止指定会话的流：前端中止该会话的 SSE 连接（即时反应），
  // 同时调用后端取消接口，让 agent 尽早停下并持久化部分内容。
  const stopStreaming = useCallback(
    (sessionId?: string | null) => {
      const target = sessionId ?? selectedId;
      if (!target) return;
      abortControllersRef.current.get(target)?.abort();
      void cancelSessionGeneration(target).catch(() => undefined);
    },
    [selectedId],
  );

  // 用户插话（steering）：agent 执行中主动补充信息。乐观渲染带
  // SUPPLEMENT_PREFIX 前缀的用户气泡后走 /inject 通道；后端无活跃流
  // （409）或请求失败时移除乐观气泡并返回 false，由调用方降级常规发送
  // （此时插话语义上就是新一轮消息）。
  const sendSupplement = useCallback(
    async (sessionId: string, content: string): Promise<boolean> => {
      const trimmed = content.trim();
      if (!trimmed) return false;
      const optimisticId = `local-user-${Date.now()}`;
      const optimistic: ChatMessage = {
        id: optimisticId,
        role: "user",
        content: `${SUPPLEMENT_PREFIX} ${trimmed}`,
        created_at: new Date().toISOString(),
        tools: [],
      };
      setSessionMessages(sessionId, (prev) => [...prev, optimistic]);
      try {
        const result = await injectSupplement(sessionId, trimmed);
        if (!result?.ok) throw new Error("inject rejected");
        return true;
      } catch {
        setSessionMessages(sessionId, (prev) => prev.filter((item) => item.id !== optimisticId));
        return false;
      }
    },
    [setSessionMessages],
  );

  return { sendSupplement, sendMessage, stopStreaming, retryCloud };
}
