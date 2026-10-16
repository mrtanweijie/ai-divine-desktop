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
  type SurfaceActionInput,
} from "@/services/api";
import { requestRaw } from "@/services/request";
import { consumeSSE } from "@/services/sse";
import { readThemePreference, resolveTheme } from "@/services/theme";
import { createStreamBuffer } from "@/pages/chat/hooks/streamBuffer";
import type {
  SurfaceSubmitOptions,
  SurfaceSubmitResult,
} from "@/pages/chat/hooks/ChatStreamContext";
import { setSessionEffort } from "@/pages/chat/state/sessionEffort";
import { setSessionModelId } from "@/pages/chat/state/sessionModel";
import { emitEventsChanged, emitTasksChanged } from "@/services/scheduledTasks";
import {
  changedFilePathsFromResult,
  changedFileRel,
  mergeLocalTools,
  settleInFlightTools,
  SUPPLEMENT_PREFIX,
  upsertSubAgent,
  upsertTool,
} from "@/pages/chat/chatUtils";
import { parseA2UIFrame } from "@/pages/chat/components/UISurface/parseUISurface";
import type { UISurface } from "@/pages/chat/components/UISurface/types";
import { markSurfaceClosed, upsertSurface } from "@/pages/chat/state/surfaceStore";
import type {
  ApprovalMode,
  ChatFile,
  ChatMessage,
  MentionRef,
  Project,
  Session,
  SubAgentItem,
  TodoItem,
  ToolEvent,
} from "@/types";

/**
 * 局部更新某条消息的 `surfaces`，**引用不变则返回原数组**。
 *
 * 这是消息级面板（design 028 §5.2）唯一允许的写入路径：
 * `MessageItem` 是 `memo` 的，若这里在"没有实际变化"时也返回新数组，
 * 流式期间每个 chunk 都会让全部历史消息白重渲染（044 §16.3）。
 */
function patchMessageSurfaces(
  messages: ChatMessage[],
  messageId: string,
  update: (surfaces: UISurface[] | undefined) => UISurface[],
): ChatMessage[] {
  let changed = false;
  const next = messages.map((message) => {
    if (message.id !== messageId) return message;
    const surfaces = update(message.surfaces);
    if (surfaces === message.surfaces) return message;
    changed = true;
    return { ...message, surfaces };
  });
  return changed ? next : messages;
}

/**
 * 把一帧面板写到**它该在的那条消息**上（044 §8.3「面板原地刷新」）。
 *
 * 默认写到本轮 assistant 消息；但若同一 `surfaceId` 已经挂在**别的**
 * 消息上（上一回合那块面板），就写回那条 —— 用户看到的是面板原地更新，
 * 而不是"下方又长出一块"。模型想新开一块面板时会用新的 `surfaceId`。
 *
 * 返回值引用不变 = 这一帧被 `seq` 判定为过期/重复（`upsertSurface` 丢弃），
 * 保证 `MessageItem` 的 memo 不因无变化而失效。
 */
function writeSurfaceFrame(
  messages: ChatMessage[],
  assistantId: string,
  surface: UISurface,
): ChatMessage[] {
  let ownerId: string | null = null;
  for (const message of messages) {
    if (message.id === assistantId) continue;
    if (message.surfaces?.some((item) => item.surfaceId === surface.surfaceId)) {
      ownerId = message.id;
      break;
    }
  }
  return patchMessageSurfaces(messages, ownerId ?? assistantId, (surfaces) =>
    upsertSurface(surfaces, surface),
  );
}

/** `deleteSurface`：面板可能挂在任何一条消息上，全量找一遍再收起。 */
function closeSurfaceEverywhere(messages: ChatMessage[], surfaceId: string): ChatMessage[] {
  let changed = false;
  const next = messages.map((message) => {
    if (!message.surfaces?.some((item) => item.surfaceId === surfaceId)) return message;
    const surfaces = markSurfaceClosed(message.surfaces, surfaceId);
    if (surfaces === message.surfaces) return message;
    changed = true;
    return { ...message, surfaces };
  });
  return changed ? next : messages;
}

// `/技能` 未被真正使用的提示要挂在**本轮回复**上（方案 025 §3.3 校验闭环）：
// done 后会话会从服务端整段恢复，消息 id 换成服务端 id，所以统一按
// “最后一条 assistant 消息”回填，避免提示落空。
function attachUnusedMentions(messages: ChatMessage[], unused: string[]): ChatMessage[] {
  if (!unused.length) return messages;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "assistant") {
      const next = [...messages];
      next[index] = { ...next[index], unused_mentions: unused };
      return next;
    }
  }
  return messages;
}

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
  //
  // `options.silent`（面板动作的静默回合，design 028 §8.5）：除面板帧与收尾
  // （done / error）外**一切产出都不落消息** —— 那一轮不该长出气泡，模型正文
  // 由后端降级成面板底部的 `surface_note`。
  const buildStreamHandlers = useCallback(
    (sessionId: string, assistantId: string, options: { silent?: boolean } = {}) => {
      const silent = options.silent === true;
      // B2：文本增量先进缓冲区，rAF 帧对齐合并成一次 setSessionMessages，
      // 渲染频率从每 chunk 一次降到 ≤60Hz；think 与 content 同帧一次提交。
      const buffer = createStreamBuffer(({ think, content }) => {
        if (silent) return;
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
        // A2UI 面板帧（044 §5.1）。后端保证**帧内消息完整**（一条 A2UI 消息不跨帧），
        // 因此这里解析出的永远是一整块 surface；非法帧只告警、不崩（纵深防御 L3）。
        a2ui: (data: unknown) => {
          const parsed = parseA2UIFrame(data, { messageId: assistantId });
          // 注意：这里只能判 `in`，不能写成 `"deleted" in parsed && parsed.deleted`
          // —— 复合条件会让 TS 无法收窄联合（`!A` 与 `A && !B` 两种情况都要保留），
          // 于是下面的 `parsed.ok` 会报「属性不存在」。该分支的 `deleted` 恒为 true，
          // 单判 `in` 即可。
          if ("deleted" in parsed) {
            setSessionMessages(sessionId, (prev) => closeSurfaceEverywhere(prev, parsed.surfaceId));
            return;
          }
          if (!parsed.ok) {
            console.warn("[uiSurface] 忽略非法的 a2ui 帧：", parsed.reason);
            return;
          }
          const surface = parsed.surface;
          // 写回**它原本所在的**消息：动作触发的新回合会重发同 surfaceId 的
          // 面板，那是一次原地刷新而非新开一块（044 §8.3）。
          setSessionMessages(sessionId, (prev) => writeSurfaceFrame(prev, assistantId, surface));
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
        done: async (payload: { message: string; unused_mentions?: string[] }) => {
          buffer.flush();
          const unusedMentions = payload.unused_mentions ?? [];
          setSessionMessages(sessionId, (prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    streaming: false,
                    thinking: false,
                    preprocess_pending: false,
                    unused_mentions: unusedMentions,
                    // 静默回合：面板的"更新中"态在这里收尾（流已结束，
                    // 服务端也已完成面板搬迁，下面的 getSession 会带回终态）。
                    surface_updating: false,
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
            setSessionMessages(sessionId, (prev) =>
              attachUnusedMentions(mergeLocalTools(prev, restored), unusedMentions),
            );
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
          const text = messageKey
            ? t(messageKey, { ...(messageParams ?? {}), defaultValue: message })
            : message;
          setSessionMessages(sessionId, (prev) =>
            prev.map((item) => {
              if (item.id !== assistantId) return item;
              // 静默回合没有可挂错误的助手气泡 → 错误挂在面板上（§8.5）。
              if (silent) {
                return { ...item, surface_updating: false, surface_error: text };
              }
              return { ...item, streaming: false, thinking: false, error: text };
            }),
          );
        },
      };

      if (silent) {
        // 静默回合（面板动作）：只有 a2ui 帧、done、error 与两类全局变更事件
        // 需要处理 —— 正文 / 思考 / 计划 / 工具卡都不该出现在任何气泡里。
        handlers.think = () => undefined;
        handlers.think_done = () => undefined;
        handlers.message = () => undefined;
        handlers.plan = () => undefined;
        handlers.plan_sync = () => undefined;
        handlers.todo_update = () => undefined;
        handlers.tool = () => undefined;
        handlers.subagent = () => undefined;
      }

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
    async (question: string, files: ChatFile[], mentions: MentionRef[], effort: string) => {
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
            // `@文件` / `/技能` 的结构化引用：后端只信这里，不从正文反向解析
            ...(mentions.length > 0 ? { mentions } : {}),
          }),
        });
        await consumeSSE(response, handlers);
      } catch (error) {
        // 中断/网络错误时先把缓冲区里的增量落上屏，避免丢尾字
        buffer.flush();
        if (controller.signal.aborted) {
          // 主动点击停止：中止连接，不显示错误，只结束流式态。
          // 在跑的工具必须一并结算：连接已断，它们收不到后续 done 事件，
          // 不结算就会永久停在 loading（状态对齐刷新后的结果）。
          setSessionMessages(sessionId, (prev) =>
            prev.map((item) =>
              item.id === assistantMessage.id
                ? {
                    ...item,
                    streaming: false,
                    thinking: false,
                    tools: settleInFlightTools(item.tools),
                  }
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

  /**
   * A2UI 面板动作 → 新回合（design 028 §8）。
   *
   * 走的是**和打字完全同一条管线**：后端把动作落成一条可见 user 消息，
   * 再跑一轮常规 `/stream_chat`。这里复用 `buildStreamHandlers`，所以
   * 新一轮吐出的面板会自动写回原处（`writeSurfaceFrame`），用户看到的
   * 是"面板原地刷新"（§8.3）。agent 内核零侵入。
   *
   * 三条前端纪律：
   * 1. **不排队**：该会话已有活跃流就直接返回 `busy`，由调用方提示
   *    （后端也会 409，这里是省一次往返）。插话（steering）才是"排队"语义。
   * 2. **失败要撤**：请求根本没跑起来（网络错/409/404）时，把乐观追加的
   *    user + assistant 两条一起撤掉 —— 否则历史里会留下一条没有回答的问题。
   * 3. **失败不丢状态**：面板里的值仍由 `uiSurfaceStateStore` 持有，
   *    用户再点一次即可，不做自动重试（重试是用户意图，不是系统猜测）。
   */
  const submitSurfaceAction = useCallback(
    async (
      input: SurfaceActionInput,
      effort: string,
      options?: SurfaceSubmitOptions,
    ): Promise<SurfaceSubmitResult> => {
      const sessionId = input.sessionId;
      if (!sessionId || !input.name) return { ok: false, reason: "failed" };
      // 用 abortControllers 而不是 streaming prop 判忙：后者只反映**当前选中**
      // 会话的流态，而面板属于它自己那条会话。
      if (abortControllersRef.current.has(sessionId)) return { ok: false, reason: "busy" };

      const think = effort !== "off";
      // 静默回合（design 028 §8.5）：**不追加乐观气泡**。面板动作的全部意义是
      // "面板原地刷新"，多出来的 user + assistant 两条气泡会把用户正在看的
      // 那块面板顶出视口 —— 用户报告的就是这个。
      //
      // 流事件仍要有承载者：直接挂到**面板所属的那条消息**上（服务端认这个 id，
      // 收尾时也会把新面板搬回它）。`surface_updating` 是纯本地标记。
      const targetId = input.messageId;
      if (!targetId) return { ok: false, reason: "failed" };
      setSessionMessages(sessionId, (prev) =>
        prev.map((message) =>
          message.id === targetId
            ? { ...message, surface_updating: true, surface_error: undefined }
            : message,
        ),
      );
      setSessionStreaming(sessionId, true);

      const controller = new AbortController();
      abortControllersRef.current.set(sessionId, controller);
      const { buffer, handlers } = buildStreamHandlers(sessionId, targetId, { silent: true });
      /** 回合根本没跑起来 → 撤掉"更新中"标记（面板内容保持原样）。 */
      const rollback = () =>
        setSessionMessages(sessionId, (prev) =>
          prev.map((message) =>
            message.id === targetId ? { ...message, surface_updating: false } : message,
          ),
        );

      let response: Response;
      try {
        response = await requestRaw("/chat/surface-action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({
            session_id: sessionId,
            message_id: input.messageId,
            surface_id: input.surfaceId,
            action_id: input.actionId,
            name: input.name,
            label: input.label,
            context: input.context,
            data_model: input.dataModel,
            approval_mode: approvalMode,
            think,
            ...(think ? { reasoning_effort: effort } : {}),
            ...(modelId ? { model_id: modelId } : {}),
            locale: i18next.language || "zh-CN",
            // 传 resolved 值（dark/light），不传 preference——后端不认 "system"
            ui_theme: resolveTheme(readThemePreference()),
          }),
        });
      } catch (error) {
        buffer.dispose();
        rollback();
        abortControllersRef.current.delete(sessionId);
        setSessionStreaming(sessionId, false);
        console.error("[uiSurface] surface-action 请求失败", error);
        return { ok: false, reason: "failed" };
      }

      if (!response.ok) {
        buffer.dispose();
        rollback();
        abortControllersRef.current.delete(sessionId);
        setSessionStreaming(sessionId, false);
        if (response.status === 409) return { ok: false, reason: "busy" };
        if (response.status === 404) return { ok: false, reason: "disabled" };
        return { ok: false, reason: "failed" };
      }

      // 走到这里回合已经起了：通知面板清掉用户编辑态（§8.3）——
      // 必须在**消费流之前**，否则新一轮刷回来的面板会先被旧编辑态覆盖一遍。
      options?.onAccepted?.();

      // 后续失败按普通流错误处理。静默回合没有助手气泡可挂错误，
      // 一律落到面板上（surface_error），面板内容保持用户填的那份。
      try {
        await consumeSSE(response, handlers);
        return { ok: true };
      } catch (error) {
        buffer.flush();
        if (controller.signal.aborted) {
          setSessionMessages(sessionId, (prev) =>
            prev.map((item) =>
              item.id === targetId
                ? { ...item, surface_updating: false, streaming: false, thinking: false }
                : item,
            ),
          );
        } else {
          const text =
            error instanceof Error
              ? error.message
              : t("chat.requestFailed", "请求失败，请稍后重试");
          setSessionMessages(sessionId, (prev) =>
            prev.map((item) =>
              item.id === targetId
                ? { ...item, surface_updating: false, surface_error: text }
                : item,
            ),
          );
        }
        return { ok: false, reason: "failed" };
      } finally {
        buffer.dispose();
        if (abortControllersRef.current.get(sessionId) === controller) {
          abortControllersRef.current.delete(sessionId);
        }
        setSessionStreaming(sessionId, false);
      }
    },
    [approvalMode, buildStreamHandlers, modelId, setSessionMessages, setSessionStreaming, t],
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

  return { sendSupplement, sendMessage, stopStreaming, retryCloud, submitSurfaceAction };
}
