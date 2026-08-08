import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createSession,
  deleteSession,
  getSession,
  getSettings,
  getWorkspace,
  listSessions,
  messagesToChatMessages,
  renameSession,
  updateSettings,
  apiBase,
} from "@/services/api";
import { consumeSSE } from "@/services/sse";
import { ChatHeader } from "@/pages/chat/components/ChatHeader";
import { ChatInput } from "@/pages/chat/components/ChatInput";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { MessageList } from "@/pages/chat/components/MessageList";
import { SessionList } from "@/pages/chat/components/SessionList";
import { SettingsModal } from "@/components/SettingsModal";
import type {
  ChatFile,
  ChatMessage,
  Settings,
  TodoItem,
  ToolEvent,
} from "@/types";
import { useConfigState } from "@/pages/chat/state/configStore";
import { useFullscreen } from "@/pages/chat/state/fullscreenStore";
import { useInputState } from "@/pages/chat/state/inputStore";
import { useMessageState } from "@/pages/chat/state/messageStore";
import { useSessionState } from "@/pages/chat/state/sessionStore";
import { Flex } from "@/components/ui/Flex";
import { TitleBar } from "@/components/TitleBar";
import { SessionSearchModal } from "@/pages/chat/components/SessionList/SessionSearchModal";

export default function ChatPage() {
  const { sessions, setSessions, selectedId, setSelectedId } =
    useSessionState();
  const { messages, setMessages, streaming, setStreaming } =
    useMessageState();
  const { settings, setSettings, setWorkspace } = useConfigState();
  const {
    sidebarOpen,
    setSidebarOpen,
    settingsOpen,
    setSettingsOpen,
    confirmState,
    setConfirmState,
  } = useInputState();
  const fullscreen = useFullscreen();
  const [searchOpen, setSearchOpen] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  const refreshSessions = useCallback(async () => {
    const data = await listSessions();
    setSessions(data.sessions);
    return data.sessions;
  }, []);

  const refreshWorkspace = useCallback(async () => {
    try {
      const data = await getWorkspace();
      setWorkspace(data.categories);
    } catch {
      setWorkspace([]);
    }
  }, []);

  const loadSession = useCallback(async (id: string) => {
    const data = await getSession(id);
    setSelectedId(id);
    setMessages(
      messagesToChatMessages(data.messages, data.tool_runs ?? [], data.todos)
    );
  }, []);

  useEffect(() => {
    Promise.all([refreshSessions(), getSettings(), refreshWorkspace()])
      .then(async ([sessionList, currentSettings]) => {
        setSettings(currentSettings);
        if (sessionList.length > 0) {
          await loadSession(sessionList[0].id);
        }
      })
      .catch(() => {
        setSettings({
          provider: "mock",
          base_url: "",
          model: "deepseek-v4-flash",
          has_api_key: false,
          has_glm_key: false,
          workspace_dir: "",
          username: "用户",
          think_default: false,
          context_limit: 20,
          tools: [],
        });
      });
  }, [loadSession, refreshSessions, refreshWorkspace]);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1100) {
        setSidebarOpen(false);
      }
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [setSidebarOpen]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.key.toLowerCase() === "n") {
        event.preventDefault();
        void handleNewSession();
      }
      if (event.ctrlKey && event.key.toLowerCase() === "f") {
        event.preventDefault();
        document.getElementById("session-search")?.focus();
      }
      if (event.ctrlKey && event.key.toLowerCase() === "k") {
        event.preventDefault();
        composerRef.current?.focus();
      }
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "t") {
        event.preventDefault();
        if (settings) {
          setSettings({ ...settings, think_default: !settings.think_default });
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  const closeSidebarForNarrow = useCallback(() => {
    if (typeof window !== "undefined" && window.innerWidth < 1100) {
      setSidebarOpen(false);
    }
  }, [setSidebarOpen]);

  const handleNewSession = useCallback(async () => {
    const session = await createSession();
    setSessions((prev) => [session, ...prev]);
    setSelectedId(session.id);
    setMessages([]);
    closeSidebarForNarrow();
    setTimeout(() => composerRef.current?.focus(), 0);
  }, [closeSidebarForNarrow]);

  const handleSelectSession = useCallback(
    async (id: string) => {
      if (streaming) return;
      await loadSession(id);
      closeSidebarForNarrow();
    },
    [closeSidebarForNarrow, loadSession, streaming]
  );

  const handleRename = useCallback(
    async (id: string, title: string) => {
      if (!title.trim()) return;
      await renameSession(id, title.trim());
      await refreshSessions();
    },
    [refreshSessions]
  );

  const handleDelete = useCallback(
    (id: string) => {
      setConfirmState({
        title: "删除会话",
        description: "删除后该会话的消息和工具记录将无法恢复。",
        action: async () => {
          await deleteSession(id);
          const remaining = await refreshSessions();
          if (id === selectedId) {
            if (remaining.length > 0) {
              await loadSession(remaining[0].id);
            } else {
              setSelectedId(null);
              setMessages([]);
            }
          }
          setConfirmState(null);
        },
      });
    },
    [loadSession, refreshSessions, selectedId]
  );

  const handleSettingsSave = useCallback(
    async (
      body: Partial<Settings> & { api_key?: string; glm_api_key?: string }
    ) => {
      const updated = await updateSettings(body);
      setSettings(updated);
      setSettingsOpen(false);
      await refreshWorkspace();
    },
    [refreshWorkspace]
  );

  const sendMessage = useCallback(
    async (question: string, files: ChatFile[], think: boolean) => {
      const trimmed = question.trim();
      if (!trimmed || streaming) return;
      let sessionId = selectedId;
      if (!sessionId) {
        const session = await createSession();
        sessionId = session.id;
        setSessions((prev) => [session, ...prev]);
        setSelectedId(session.id);
      }

      const userMessage: ChatMessage = {
        id: `local-user-${Date.now()}`,
        role: "user",
        content: trimmed,
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
      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setStreaming(true);

      try {
        const response = await fetch(`${apiBase()}/stream_chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: trimmed,
            session_id: sessionId,
            think,
            attachments: files.map((file) => ({
              name: file.name,
              ...(file.path
                ? { file_path: file.path }
                : { content: file.content ?? "" }),
            })),
          }),
        });
        await consumeSSE(response, {
          think: ({ content }) => {
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantMessage.id
                  ? { ...message, think: (message.think ?? "") + content }
                  : message
              )
            );
          },
          message: ({ content }) => {
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantMessage.id
                  ? { ...message, content: message.content + content }
                  : message
              )
            );
          },
          plan: (data) => {
            const items = (data.items ?? []) as unknown as TodoItem[];
            setMessages((prev) =>
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
            setMessages((prev) =>
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
            setMessages((prev) =>
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
          done: async () => {
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantMessage.id
                  ? { ...message, streaming: false }
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
              setMessages((prev) => mergeLocalTools(prev, restored));
            }
            await Promise.all([refreshSessions(), refreshWorkspace()]);
          },
          error: ({ message }) => {
            setMessages((prev) =>
              prev.map((item) =>
                item.id === assistantMessage.id
                  ? {
                      ...item,
                      streaming: false,
                      error: message,
                    }
                  : item
              )
            );
          },
        });
      } catch (error) {
        setMessages((prev) =>
          prev.map((item) =>
            item.id === assistantMessage.id
              ? {
                  ...item,
                  streaming: false,
                  error:
                    error instanceof Error ? error.message : "请求失败，请稍后重试",
                }
              : item
          )
        );
      } finally {
        setStreaming(false);
      }
    },
    [refreshSessions, refreshWorkspace, selectedId, streaming]
  );

  const currentSession = useMemo(
    () => sessions.find((session) => session.id === selectedId) ?? null,
    [selectedId, sessions]
  );

  return (
    <Flex className={`app-shell ${sidebarOpen ? "sidebar-visible" : ""}`}>
      <Flex
        direction="column"
        className={`left-panel${!sidebarOpen ? " collapsed" : ""}`}
      >
      <TitleBar
        collapsed={!sidebarOpen}
        onToggleCollapse={() => setSidebarOpen((value) => !value)}
        onOpenSearch={() => setSearchOpen(true)}
        fullscreen={fullscreen}
      />
        <SessionList
          sessions={sessions}
          selectedId={selectedId}
          collapsed={!sidebarOpen}
          onSelect={handleSelectSession}
          onNew={handleNewSession}
          onRename={handleRename}
          onDelete={handleDelete}
          onOpenSettings={() => setSettingsOpen(true)}
        />
      </Flex>
      <Flex
        direction="column"
        className="main-area"
        style={{ flex: 1, minWidth: 0 }}
      >
        <ChatHeader
          session={currentSession}
          model={settings?.model ?? ""}
          think={settings?.think_default ?? false}
          onThinkChange={(value) =>
            setSettings((prev) => (prev ? { ...prev, think_default: value } : prev))
          }
          onOpenSidebar={() => setSidebarOpen(true)}
          onRename={handleRename}
        />
        <MessageList
          messages={messages}
          streaming={streaming}
          sessionId={selectedId}
          username={settings?.username || "用户"}
        />
        <ChatInput
          ref={composerRef}
          disabled={streaming}
          onSend={(question, files) =>
            void sendMessage(
              question,
              files,
              settings?.think_default ?? false
            )
          }
        />
      </Flex>
      <SessionSearchModal
        open={searchOpen}
        sessions={sessions}
        selectedId={selectedId}
        onClose={() => setSearchOpen(false)}
        onSelect={handleSelectSession}
      />
      {settingsOpen && settings && (
        <SettingsModal
          settings={settings}
          onClose={() => setSettingsOpen(false)}
          onSave={(body) => void handleSettingsSave(body)}
        />
      )}
      {confirmState && (
        <ConfirmDialog
          title={confirmState.title}
          description={confirmState.description}
          onConfirm={() => void confirmState.action()}
          onCancel={() => setConfirmState(null)}
        />
      )}
    </Flex>
  );
}

function upsertTool(tools: ToolEvent[], next: ToolEvent): ToolEvent[] {
  const index = tools.findIndex((tool) => tool.tool === next.tool);
  if (index === -1) {
    return [...tools, { ...next, status: next.status || "preparing" }];
  }
  const updated = [...tools];
  updated[index] = { ...updated[index], ...next };
  return updated;
}

function mergeLocalTools(local: ChatMessage[], restored: ChatMessage[]) {
  if (local.length !== restored.length) return restored;
  return restored.map((message, index) => ({
    ...message,
    tools: local[index]?.tools?.length ? local[index].tools : message.tools,
    files: local[index]?.files?.length ? local[index].files : message.files,
  }));
}
