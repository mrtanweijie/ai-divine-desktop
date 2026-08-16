// Owns the POST /stream_chat SSE flow for a chat page instance.
import { useCallback } from "react";
import type {
  Dispatch,
  MutableRefObject,
  SetStateAction,
} from "react";
import type { TFunction } from "i18next";
import i18next from "@/i18n";
import {
  createSession,
  getSession,
  messagesToChatMessages,
} from "@/services/api";
import { requestRaw } from "@/services/request";
import { consumeSSE } from "@/services/sse";
import { setSessionEffort } from "@/pages/chat/state/sessionEffort";
import {
  emitEventsChanged,
  emitTasksChanged,
} from "@/services/scheduledTasks";
import {
  changedFilePathsFromResult,
  changedFileRel,
  mergeLocalTools,
  upsertTool,
} from "@/pages/chat/chatUtils";
import type {
  ApprovalMode,
  ChatFile,
  ChatMessage,
  Project,
  Session,
  TodoItem,
  ToolEvent,
} from "@/types";

interface UseChatStreamOptions {
  selectedId: string | null;
  selectedProjectId: string | null;
  projects: Project[];
  approvalMode: ApprovalMode;
  streaming: boolean;
  workspacePanelOpenRef: MutableRefObject<boolean>;
  setSessions: Dispatch<SetStateAction<Session[]>>;
  setSelectedId: (id: string | null) => void;
  setSessionMessages: (
    sessionId: string | null,
    messages: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])
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

  const sendMessage = useCallback(
    async (
      question: string,
      files: ChatFile[],
      effort: string
    ) => {
      // "off" disables deep thinking; any other value enables it at that
      // reasoning effort level.
      const think = effort !== "off";
      // Optimistically append user/assistant messages, then stream SSE events
      // into the assistant message and finally restore server-persisted state.
      const trimmed = question.trim();
      if ((!trimmed && files.length === 0) || streaming) return;
      const effectiveQuestion =
        trimmed || t("chat.analyzeAttachment", "请分析附件");
      let sessionId = selectedId;
      if (!sessionId) {
        const projectId = selectedProjectId ?? projects[0]?.id ?? null;
        if (!projectId) return;
        const session = await createSession(
          undefined,
          projectId,
          approvalMode,
          i18next.language || "zh-CN"
        );
        sessionId = session.id;
        setSessions((prev) => [session, ...prev]);
        setSelectedId(session.id);
        // 新会话首次发送即记住本条消息使用的深度思考档位。
        setSessionEffort(session.id, effort);
      }

      const userMessage: ChatMessage = {
        id: `local-user-${Date.now()}`,
        role: "user",
        content: effectiveQuestion,
        created_at: new Date().toISOString(),
        tools: [],
        files,
      };
      const assistantMessage: ChatMessage = {
        id: `local-assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
        tools: [],
        streaming: true,
      };
      setSessionMessages(
        sessionId,
        (prev) => [...prev, userMessage, assistantMessage]
      );
      setSessionStreaming(sessionId, true);

      try {
        const response = await requestRaw("/stream_chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: effectiveQuestion,
            session_id: sessionId,
            approval_mode: approvalMode,
            think,
            ...(think ? { reasoning_effort: effort } : {}),
            locale: i18next.language || "zh-CN",
            attachments: files.map((file) => ({
              name: file.name,
              size: file.size,
              ...(file.path
                ? { file_path: file.path }
                : { content: file.content ?? "" }),
            })),
          }),
        });
        await consumeSSE(response, {
          think: ({ content }) => {
            setSessionMessages(sessionId, (prev) =>
              prev.map((message) =>
                message.id === assistantMessage.id
                  ? {
                      ...message,
                      think: (message.think ?? "") + content,
                      thinking: true,
                    }
                  : message
              )
            );
          },
          think_done: () => {
            setSessionMessages(sessionId, (prev) =>
              prev.map((message) =>
                message.id === assistantMessage.id
                  ? { ...message, thinking: false }
                  : message
              )
            );
          },
          message: ({ content }) => {
            setSessionMessages(sessionId, (prev) =>
              prev.map((message) =>
                message.id === assistantMessage.id
                  ? {
                      ...message,
                      content: message.content + content,
                      thinking: false,
                    }
                  : message
              )
            );
          },
          plan: (data) => {
            const items = (data.items ?? []) as unknown as TodoItem[];
            setSessionMessages(sessionId, (prev) =>
              prev.map((message) =>
                message.id === assistantMessage.id
                  ? { ...message, todos: items }
                  : message
              )
            );
          },
          todo_update: (data) => {
            const next = data as {
              id: string;
              status: TodoItem["status"];
              result?: string;
            };
            setSessionMessages(sessionId, (prev) =>
              prev.map((message) =>
                message.id === assistantMessage.id
                  ? {
                      ...message,
                      todos: (message.todos ?? []).map((todo) =>
                        todo.id === next.id
                          ? { ...todo, status: next.status, result: next.result }
                          : todo
                      ),
                    }
                  : message
              )
            );
          },
          tool: (data) => {
            const event = data as unknown as ToolEvent;
            if (event.status === "done" && event.result) {
              const projectPath = projects.find(
                (item) => item.id === selectedProjectId
              )?.path;
              if (projectPath) {
                for (const filePath of changedFilePathsFromResult(
                  event.result
                )) {
                  const rel = changedFileRel(projectPath, filePath);
                  if (rel && workspacePanelOpenRef.current) {
                    setAgentChangedFiles((prev) => new Set(prev).add(rel));
                  }
                }
              }
            }
            setSessionMessages(sessionId, (prev) =>
              prev.map((message) =>
                message.id === assistantMessage.id
                  ? {
                      ...message,
                      tools: upsertTool(message.tools, event),
                    }
                  : message
              )
            );
          },
          scheduled_tasks_changed: () => {
            emitTasksChanged();
          },
          calendar_events_changed: () => {
            emitEventsChanged();
          },
          done: async () => {
            setSessionMessages(sessionId, (prev) =>
              prev.map((message) =>
                message.id === assistantMessage.id
                  ? { ...message, streaming: false, thinking: false }
                  : message
              )
            );
            if (sessionId) {
              const data = await getSession(sessionId);
              const restored = messagesToChatMessages(
                data.messages,
                data.tool_runs ?? [],
                data.todos
              );
              setSessionMessages(sessionId, (prev) => mergeLocalTools(prev, restored));
              setHasMoreOlder(false);
              setOldestMessageId(null);
            }
            await Promise.all([
              refreshSessions(selectedProjectId),
              refreshProjects(),
              refreshWorkspace(),
            ]);
            if (sessionId && workspacePanelOpenRef.current) {
              await loadChangedFiles(sessionId);
            }
          },
          error: ({ message, messageKey, messageParams }) => {
            setSessionMessages(sessionId, (prev) =>
              prev.map((item) =>
                item.id === assistantMessage.id
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
                  : item
              )
            );
          },
        });
      } catch (error) {
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
              : item
          )
        );
      } finally {
        // 多会话并发：每个流的收尾只清理它自己的会话标记，
        // 与其它会话是否在流式无关。
        setSessionStreaming(sessionId, false);
      }
    },
    [
      approvalMode,
      loadChangedFiles,
      projects,
      refreshProjects,
      refreshSessions,
      refreshWorkspace,
      selectedId,
      selectedProjectId,
      setAgentChangedFiles,
      setSessionMessages,
      setSelectedId,
      setSessions,
      setHasMoreOlder,
      setSessionStreaming,
      setOldestMessageId,
      streaming,
      t,
      workspacePanelOpenRef,
    ]
  );

  return { sendMessage };
}
