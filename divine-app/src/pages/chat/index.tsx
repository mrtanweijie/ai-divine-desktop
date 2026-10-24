import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { toast } from "@/components/ui/Toast";
import { X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import {
  createProject,
  deleteProject,
  deleteSession,
  getGitInfo,
  getSettings,
  getWorkspace,
  listProjects,
  renameSession,
  updateProject,
  updateSessionApprovalMode,
  updateSettings,
} from "@/services/api";
import { ScheduledTasksPage } from "@/pages/tasks";
import { SkillsPage } from "@/pages/skills";
import { ChatHeader } from "@/pages/chat/components/ChatHeader";
import { ChatInput } from "@/pages/chat/components/ChatInput";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { MessageList } from "@/pages/chat/components/MessageList";
import { NewChatGuide } from "@/pages/chat/components/NewChatGuide";
import { FilePreviewPanel } from "@/pages/chat/components/FilePreviewPanel";
import { SessionList } from "@/pages/chat/components/SessionList";
import { SettingsModal } from "@/components/SettingsModal";
import { isMacosDesktop } from "@/services/tauri";
import { subscribeAppEvent } from "@/services/events";
import { notifyTaskFinished } from "@/services/scheduledTasks";
import type { ApprovalMode, ChatFile, ChatMessage, Project, SettingsSaveBody } from "@/types";
import { useConfigState } from "@/pages/chat/state/configStore";
import { useFullscreen } from "@/pages/chat/state/fullscreenStore";
import { useInputState } from "@/pages/chat/state/inputStore";
import { useMessageState } from "@/pages/chat/state/messageStore";
import { useShortcutAction } from "@/hooks/useShortcuts";
import { useSessionState, writeLastSessionSelection } from "@/pages/chat/state/sessionStore";
import { defaultComposerEffort, setSessionEffort } from "@/pages/chat/state/sessionEffort";
import {
  getSessionModelId,
  resolveModelTargetId,
  setSessionModelId,
} from "@/pages/chat/state/sessionModel";
import { Flex } from "@/components/ui/Flex";
import { TitleBar } from "@/components/TitleBar";
import { SessionSearchModal } from "@/pages/chat/components/SessionList/SessionSearchModal";
import { ProjectModal } from "@/pages/chat/components/ProjectModal";
import { ProjectPicker } from "@/pages/chat/components/ProjectPicker";
import { useChatStream } from "@/pages/chat/hooks/useChatStream";
import { useAppBootstrap, useSessionPreferenceSync } from "@/pages/chat/hooks/useAppBootstrap";
import {
  ChatStreamContext,
  type ChatStreamContextValue,
} from "@/pages/chat/hooks/ChatStreamContext";
import { useSessionLoader } from "@/pages/chat/hooks/useSessionLoader";
import { useWorkspacePanel } from "@/pages/chat/hooks/useWorkspacePanel";
import { expandModelId, expandModelsForSwitcher } from "@/config/providers";
import { storageSet } from "@/services/storage";
import "./index.less";
import { acceptedFilesKey } from "@/pages/chat/chatUtils";

const EMPTY_MESSAGES: ChatMessage[] = [];

export default function ChatPage() {
  const { t } = useTranslation();
  const {
    sessions,
    setSessions,
    selectedId,
    setSelectedId,
    projects,
    setProjects,
    selectedProjectId,
    setSelectedProjectId,
  } = useSessionState();
  const {
    messagesBySession,
    setSessionMessages,
    clearSessionMessages,
    streamingSessions,
    setSessionStreaming,
    getCachedSessionMessages,
  } = useMessageState();
  // 当前视图的会话消息与流状态由 selectedId 派生，支持多会话并行流式。
  const messages = selectedId ? (messagesBySession[selectedId] ?? EMPTY_MESSAGES) : EMPTY_MESSAGES;

  // 会话累计 token 消耗：汇总每条回复的 token_usage。
  const sessionTokenUsage = useMemo(() => {
    let input = 0;
    let output = 0;
    let total = 0;
    let turns = 0;
    for (const message of messages) {
      const usage = message.token_usage;
      if (!usage) continue;
      input += usage.input_tokens;
      output += usage.output_tokens;
      total += usage.total_tokens;
      turns += 1;
    }
    return { input_tokens: input, output_tokens: output, total_tokens: total, turns };
  }, [messages]);
  const streaming = selectedId ? streamingSessions.has(selectedId) : false;
  const { settings, setSettings, setWorkspace } = useConfigState();
  // 只把已配置 API Key 的模型条目按提供商 list 展开，供对话框模型切换使用。
  // 未配置 Key 的提供商不会出现在切换列表里。
  const switcherModels = useMemo(
    () => expandModelsForSwitcher((settings?.models ?? []).filter((m) => m.has_api_key)),
    [settings?.models],
  );
  // 没有任何可用模型（无 API Key 且本地模型未运行）→ 提示安装免费本地模型
  const noUsableModel = useMemo(() => {
    const models = settings?.models ?? [];
    return models.length === 0 || models.every((m) => !m.has_api_key);
  }, [settings?.models]);
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
  const [searchParams, setSearchParams] = useSearchParams();
  // 设置弹窗初始 tab（横幅"去安装本地模型"跳转到意图页）
  const [settingsInitialSection, setSettingsInitialSection] = useState<
    "basic" | "model" | "local" | "about"
  >("basic");
  // 未配置 API Key 横幅（本次会话可关闭）
  const [apiKeyBannerDismissed, setApiKeyBannerDismissed] = useState(false);
  const view = searchParams.get("view");
  const tasksOpen = view === "tasks";
  const skillsOpen = view === "skills";
  const currentSession = useMemo(
    () => sessions.find((session) => session.id === selectedId) ?? null,
    [selectedId, sessions],
  );

  const currentProject = useMemo(
    () =>
      projects.find(
        (project) => project.id === (currentSession?.project_id ?? selectedProjectId),
      ) ?? null,
    [currentSession?.project_id, projects, selectedProjectId],
  );

  // 会话切换序号：快速连点时丢弃过期的 loadSession fetch 结果
  const workspacePanelOpenRef = useRef(false);
  const workspace = useWorkspacePanel({
    selectedId,
    currentProject,
    sidebarOpen,
  });
  const {
    previewFile,
    setPreviewFile,
    workspacePanelOpen,
    setWorkspacePanelOpen,
    workspacePanelWidth,
    setWorkspacePanelWidth,
    workspaceExpanded,
    setWorkspaceExpanded,
    workspaceExpandedLayout,
    setWorkspaceExpandedLayout,
    workspaceExpandTransitioning,
    workspaceTreeWidth,
    setWorkspaceTreeWidth,
    acceptedFiles,
    setAcceptedFiles,
    handlePreviewFile,
    handleToggleWorkspaceExpand,
  } = workspace;

  useEffect(() => {
    workspacePanelOpenRef.current = workspacePanelOpen;
  }, [workspacePanelOpen]);

  const openView = useCallback(
    (nextView: "tasks" | "skills") => {
      setWorkspacePanelOpen(false);
      setWorkspaceExpanded(false);
      setWorkspaceExpandedLayout(false);
      setSearchParams({ view: nextView });
    },
    [setSearchParams, setWorkspacePanelOpen, setWorkspaceExpanded, setWorkspaceExpandedLayout],
  );
  const [projectOpen, setProjectOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [composerKey, setComposerKey] = useState(0);
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("ask");
  const [composerEffort, setComposerEffort] = useState("off");
  const [composerModelId, setComposerModelId] = useState<string | null>(null);
  // Bumped after each stream settles so the context ring refreshes usage.
  const [contextRefreshKey, setContextRefreshKey] = useState(0);
  const lastStreamingRef = useRef(false);
  const [guideCardsVisible, setGuideCardsVisible] = useState(true);
  // 无会话时显示引导卡：会话切换的派生重置用渲染期调整（React 官方建议写法，
  // 替代 set-state-in-effect 的 effect 写法）。
  const [prevSelectedIdForGuide, setPrevSelectedIdForGuide] = useState(selectedId);
  if (prevSelectedIdForGuide !== selectedId) {
    setPrevSelectedIdForGuide(selectedId);
    if (!selectedId) setGuideCardsVisible(true);
  }

  const [prefill, setPrefill] = useState<{
    text: string;
    nonce: number;
  } | null>(null);
  const [isGit, setIsGit] = useState(false);
  const [selectionReady, setSelectionReady] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  // After a stream finishes, refresh the composer context ring usage.
  useEffect(() => {
    if (lastStreamingRef.current && !streaming) {
      setContextRefreshKey((key) => key + 1);
    }
    lastStreamingRef.current = streaming;
  }, [streaming]);

  const sessionLoader = useSessionLoader({
    selectedId,
    setSelectedId,
    setSelectedProjectId,
    setSessions,
    setSessionMessages,
    getCachedSessionMessages,
    setApprovalMode,
    setWorkspaceExpanded,
    setWorkspaceExpandedLayout,
    workspacePanelOpen,
    projects,
  });
  const {
    refreshSessions,
    loadSession,
    reloadSessionMessages,
    loadOlderMessages,
    loadChangedFiles,
    hasMoreOlder,
    setHasMoreOlder,
    setOldestMessageId,
    setLoadingOlder,
    loadingOlder,
    agentChangedFiles,
    setAgentChangedFiles,
  } = sessionLoader;

  // 项目切换：重置分页与变更文件状态（工作区面板自身状态在 useWorkspacePanel
  // 内重置，previewFile 也由其处理；这里补回分页相关的 4 个）。
  useEffect(() => {
    setAgentChangedFiles(new Set());
    setHasMoreOlder(false);
    setOldestMessageId(null);
    setLoadingOlder(false);
  }, [
    currentProject?.path,
    setAgentChangedFiles,
    setHasMoreOlder,
    setOldestMessageId,
    setLoadingOlder,
  ]);

  const refreshProjects = useCallback(async () => {
    const data = await listProjects();
    setProjects(data.projects);
    return data.projects;
  }, [setProjects]);

  const refreshWorkspace = useCallback(async () => {
    try {
      const data = await getWorkspace();
      setWorkspace(data.categories);
    } catch {
      setWorkspace([]);
    }
  }, [setWorkspace]);

  useAppBootstrap({
    refreshProjects,
    refreshSessions,
    loadSession,
    setSettings,
    setComposerEffort,
    setSelectedProjectId,
    setSelectedId,
    setSelectionReady,
    t,
  });

  useSessionPreferenceSync({
    selectedId,
    settings,
    setComposerEffort,
    setComposerModelId,
  });

  useEffect(() => {
    if (!selectionReady) return;
    writeLastSessionSelection(selectedProjectId, selectedId);
  }, [selectedId, selectedProjectId, selectionReady, setSelectedId, setSelectedProjectId]);

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
    const handleOpenTasks = () => openView("tasks");
    const handleOpenSkills = () => openView("skills");
    window.addEventListener("divine:open-tasks", handleOpenTasks);
    window.addEventListener("divine:open-skills", handleOpenSkills);
    return () => {
      window.removeEventListener("divine:open-tasks", handleOpenTasks);
      window.removeEventListener("divine:open-skills", handleOpenSkills);
    };
  }, [openView]);

  const closeSidebarForNarrow = useCallback(() => {
    if (typeof window !== "undefined" && window.innerWidth < 1100) {
      setSidebarOpen(false);
    }
  }, [setSidebarOpen]);

  const handleNewSession = useCallback(
    (projectId?: string) => {
      // 多会话并发：点「新对话」不打断任何正在进行的流，
      // 只重置当前视图（messages 由 selectedId 派生，自动为空）。
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete("view");
        return next;
      });
      const safeProjectId = typeof projectId === "string" ? projectId : undefined;
      const targetProjectId =
        safeProjectId ??
        sessions.find((session) => session.id === selectedId)?.project_id ??
        selectedProjectId ??
        projects[0]?.id ??
        null;
      if (targetProjectId) {
        setSelectedProjectId(targetProjectId);
      }
      setGuideCardsVisible(true);
      setComposerKey((value) => value + 1);
      setApprovalMode("ask");
      setComposerEffort(defaultComposerEffort(settings));
      setSelectedId(null);
      closeSidebarForNarrow();
      setTimeout(() => composerRef.current?.focus(), 0);
    },
    [
      closeSidebarForNarrow,
      projects,
      selectedId,
      selectedProjectId,
      setSelectedId,
      setSearchParams,
      setSelectedProjectId,
      sessions,
      settings,
    ],
  );

  // 应用内快捷键统一走 config/keymap.ts + useShortcuts（单一监听器，
  // 修饰键按平台归一化：macOS ⌘ / 其他平台 Ctrl），不再散落硬编码。
  useShortcutAction("session.new", () => void handleNewSession());
  // 打开会话搜索弹窗（弹窗输入框自带 autoFocus）；旧实现 focus 的
  // #session-search 元素在 DOM 中不存在，快捷键一直处于落空状态
  useShortcutAction("session.search", () => setSearchOpen(true));
  useShortcutAction("composer.focus", () => composerRef.current?.focus());
  useShortcutAction("composer.toggleThinking", () => {
    if (!settings) return;
    const defaultEffort = defaultComposerEffort(settings);
    const next =
      composerEffort === "off" ? (defaultEffort === "off" ? "high" : defaultEffort) : "off";
    setComposerEffort(next);
    setSessionEffort(selectedId, next);
    setSettings({ ...settings, think_default: next !== "off" });
  });

  const handleSelectProject = useCallback(
    async (id: string) => {
      // 多会话并发：切换项目不打断任何正在进行的流。
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete("view");
        return next;
      });
      setSelectedProjectId(id);
      const remaining = await refreshSessions(id);
      if (remaining.length > 0) {
        await loadSession(remaining[0].id);
      } else {
        setGuideCardsVisible(true);
        setSelectedId(null);
      }
      closeSidebarForNarrow();
    },
    [
      closeSidebarForNarrow,
      setSelectedId,
      setSelectedProjectId,
      loadSession,
      refreshSessions,
      setSearchParams,
    ],
  );

  const handleSaveProject = useCallback(
    async (body: { name: string; path?: string; icon?: string }) => {
      if (editingProject) {
        await updateProject(editingProject.id, {
          name: body.name,
          icon: body.icon,
        });
        await refreshProjects();
        setProjectOpen(false);
        setEditingProject(null);
        return;
      }
      const project = await createProject(body);
      setProjects((prev) => [project, ...prev]);
      setSelectedProjectId(project.id);
      void refreshSessions(project.id).catch(() => undefined);
      setGuideCardsVisible(true);
      setSelectedId(null);
      setProjectOpen(false);
      closeSidebarForNarrow();
      setTimeout(() => composerRef.current?.focus(), 0);
    },
    [
      closeSidebarForNarrow,
      editingProject,
      refreshProjects,
      refreshSessions,
      setProjects,
      setSelectedId,
      setSelectedProjectId,
    ],
  );

  const handleEditProject = useCallback((project: Project) => {
    setEditingProject(project);
    setProjectOpen(true);
  }, []);

  const handleDeleteProject = useCallback(
    (id: string) => {
      const project = projects.find((item) => item.id === id);
      const sessionCount = project?.session_count ?? 0;
      setConfirmState({
        title: t("session.deleteProjectTitle", "删除项目"),
        description: t(
          "session.deleteProjectConfirm",
          "将删除项目“{{name}}”及其 {{count}} 个会话；文件夹和文件保留在磁盘上，不会删除。",
          { name: project?.name ?? "", count: sessionCount },
        ),
        action: async () => {
          await deleteProject(id);
          const remaining = await refreshProjects();
          if (id === selectedProjectId) {
            const next = remaining[0]?.id ?? null;
            setSelectedProjectId(next);
            if (next) {
              const sessionList = await refreshSessions(next);
              if (sessionList.length > 0) {
                await loadSession(sessionList[0].id);
              } else {
                setGuideCardsVisible(true);
                setSelectedId(null);
              }
            } else {
              setGuideCardsVisible(true);
              setSelectedId(null);
            }
          }
          setConfirmState(null);
        },
      });
    },
    [
      loadSession,
      projects,
      refreshProjects,
      refreshSessions,
      selectedProjectId,
      setConfirmState,
      setSelectedId,
      setSelectedProjectId,
      t,
    ],
  );

  const handleSelectSession = useCallback(
    async (id: string) => {
      const isCurrent = id === selectedId;
      // 多会话并发：切换会话不取消任何正在进行的流。
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete("view");
        return next;
      });
      if (streaming && isCurrent) {
        // 点回「正在进行的会话」：保留本地 live 消息（SSE 还在写），
        // 只切回对话视图；重载会把流式消息顶掉，导致看不到输出。
        closeSidebarForNarrow();
        return;
      }
      await loadSession(id);
      closeSidebarForNarrow();
    },
    [closeSidebarForNarrow, loadSession, selectedId, setSearchParams, streaming],
  );

  const handleRename = useCallback(
    async (id: string, title: string) => {
      if (!title.trim()) return;
      await renameSession(id, title.trim());
      await refreshSessions(selectedProjectId);
    },
    [refreshSessions, selectedProjectId],
  );

  const handleDelete = useCallback(
    (id: string) => {
      setConfirmState({
        title: t("session.deleteTitle", "删除会话"),
        description: t("session.deleteConfirm", "删除后该会话的消息和工具记录将无法恢复。"),
        action: async () => {
          await deleteSession(id);
          clearSessionMessages(id);
          const remaining = await refreshSessions(selectedProjectId);
          if (id === selectedId) {
            if (remaining.length > 0) {
              await loadSession(remaining[0].id);
            } else {
              setGuideCardsVisible(true);
              setSelectedId(null);
            }
          }
          setConfirmState(null);
        },
      });
    },
    [
      clearSessionMessages,
      loadSession,
      refreshSessions,
      selectedId,
      selectedProjectId,
      setConfirmState,
      setSelectedId,
      t,
    ],
  );

  const handleSettingsSave = useCallback(
    async (body: SettingsSaveBody) => {
      const updated = await updateSettings(body);
      setSettings(updated);
      // 设置里的默认思考档位变更后立即同步到输入框，无需新建会话。
      setComposerEffort(defaultComposerEffort(updated));
      // 默认模型变更后，若当前会话没有单独记忆的模型，立即跟随；
      // 记住/默认条目未配置 API Key 时回落到第一个已配置 Key 的提供商。
      const list = updated.models ?? [];
      const activeId = list.find((entry) => entry.active)?.id ?? null;
      const remembered = selectedId ? getSessionModelId(selectedId) : null;
      setComposerModelId(expandModelId(resolveModelTargetId(list, remembered, activeId), list));
      setSettingsOpen(false);
      await refreshWorkspace();
    },
    [refreshWorkspace, selectedId, setSettings, setSettingsOpen],
  );

  // 静默保存（不关闭弹窗）：用于设为默认等即时生效的操作
  const handleSilentSave = useCallback(
    async (body: SettingsSaveBody) => {
      const updated = await updateSettings(body);
      setSettings(updated);
      const list = updated.models ?? [];
      const activeId = list.find((entry) => entry.active)?.id ?? null;
      const remembered = selectedId ? getSessionModelId(selectedId) : null;
      setComposerModelId(expandModelId(resolveModelTargetId(list, remembered, activeId), list));
    },
    [selectedId, setSettings],
  );

  // 后台事件：调度器建了「任务专属会话」或跑完定时任务 → 刷新侧栏会话列表。
  // 这条连接常驻（services/events.ts），与对话回合内的 SSE 是两回事。
  useEffect(() => {
    return subscribeAppEvent("sessions_changed", () => {
      void refreshSessions().catch(() => undefined);
    });
  }, [refreshSessions]);

  // 后台任务往**当前打开的**会话里写了消息 → 立刻重载消息。
  // 不做这件事的话，定时任务跑完必须手动刷新页面才看得到内容。
  useEffect(() => {
    return subscribeAppEvent("session_messages_changed", (data) => {
      const changed = typeof data.session_id === "string" ? data.session_id : null;
      if (!changed || changed !== selectedId) return;
      void reloadSessionMessages(changed).catch(() => undefined);
    });
  }, [reloadSessionMessages, selectedId]);

  // 定时任务（非 reminder 类）跑完 → 弹系统通知提示用户。
  // reminder 有自己的提醒通道，后端不会再为它发这个事件。
  useEffect(() => {
    return subscribeAppEvent("task_finished", (data) => {
      const taskId = typeof data.task_id === "string" ? data.task_id : "";
      const title = typeof data.title === "string" ? data.title : "";
      if (!taskId || !title) return;
      void notifyTaskFinished(taskId, title, data.ok !== false).catch(() => undefined);
    });
  }, []);

  // 订单状态追踪结果（browser_order，design 031 §14.2）：命中/超时 toast 提示。
  useEffect(() => {
    return subscribeAppEvent("browser_order", (data) => {
      const status = typeof data.status === "string" ? data.status : "";
      const detail = typeof data.detail === "string" ? data.detail : "";
      const suffix = detail ? `：${detail}` : "";
      if (status === "success") {
        toast.success(t("chat.orderWatchSuccess", "订单状态更新") + suffix);
      } else if (status === "timeout") {
        toast.error(t("chat.orderWatchTimeout", "订单追踪超时") + suffix);
      }
    });
  }, [t]);

  const handleModelChange = useCallback(
    (modelId: string) => {
      setComposerModelId(modelId);
      setSessionModelId(selectedId, modelId);
    },
    [selectedId],
  );

  const handleApprovalModeChange = useCallback(
    (mode: ApprovalMode) => {
      setApprovalMode(mode);
      if (selectedId) {
        void updateSessionApprovalMode(selectedId, mode).catch(() => undefined);
      }
    },
    [selectedId],
  );

  const handleGuideAction = useCallback((prompt: string) => {
    setPrefill({ text: prompt, nonce: Date.now() });
    setTimeout(() => composerRef.current?.focus(), 0);
  }, []);

  const handleGuideValueChange = useCallback((hasValue: boolean) => {
    if (hasValue) {
      setGuideCardsVisible(false);
    } else {
      setGuideCardsVisible(true);
    }
  }, []);

  const { sendSupplement, sendMessage, stopStreaming, retryCloud, submitSurfaceAction } =
    useChatStream({
      selectedId,
      selectedProjectId,
      projects,
      approvalMode,
      streaming,
      modelId: composerModelId,
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
    });

  const handleStopStreaming = useCallback(() => {
    if (!selectedId) return;
    // 立即清除当前会话的流状态（按钮/光标即时恢复），
    // stopStreaming 中止该会话的 SSE 连接并通知后端取消。
    setSessionStreaming(selectedId, false);
    stopStreaming(selectedId);
  }, [selectedId, setSessionStreaming, stopStreaming]);

  // 用户插话（steering）：流式执行中主动补充信息。后端无活跃流（409）
  // 或注入失败时降级为常规发送（语义即新一轮消息）。
  const handleSupplement = useCallback(
    (text: string) => {
      if (!selectedId) return;
      void sendSupplement(selectedId, text).then((ok) => {
        // 降级发送不携带引用：插话是纯文本通道
        if (!ok) void sendMessage(text, [], [], composerEffort);
      });
    },
    [selectedId, sendSupplement, sendMessage, composerEffort],
  );

  // 本地模型回答的【重答】：用云端重答同一条问题（复用当前思考档位）。
  const handleRetryCloud = useCallback(
    (messageId: string) => {
      void retryCloud(messageId, composerEffort);
    },
    [composerEffort, retryCloud],
  );

  // 供消息渲染层的可点击组件（如风格选择卡片、A2UI 面板）发送消息 / 提交面板动作。
  const chatStreamValue = useMemo<ChatStreamContextValue>(
    () => ({
      sendMessage: (question: string, files: ChatFile[] = [], effort?: string) => {
        void sendMessage(question, files, [], effort ?? composerEffort);
      },
      // 面板动作也走输入框当前的深度思考档位：用户在同一个会话里，
      // 不该因为"点了按钮"而不是"打了字"就换一套模型参数。
      submitSurfaceAction: (input, options) => submitSurfaceAction(input, composerEffort, options),
      effort: composerEffort,
    }),
    [sendMessage, submitSurfaceAction, composerEffort],
  );

  const handleAcceptFile = useCallback(
    (relPath: string) => {
      setAgentChangedFiles((prev) => {
        const next = new Set(prev);
        next.delete(relPath);
        return next;
      });
      setAcceptedFiles((prev) => {
        const next = new Set(prev);
        next.add(relPath);
        if (currentProject?.path) {
          storageSet(acceptedFilesKey(currentProject.path), [...next]);
        }
        return next;
      });
    },
    [currentProject, setAcceptedFiles, setAgentChangedFiles],
  );

  // Git 项目检测（从 ChatHeader 上移到 ChatPage，避免级联渲染 FileTree）
  const gitFetchIdRef = useRef(0);
  const isGitRef = useRef(false);
  useEffect(() => {
    if (!currentProject?.path) {
      if (isGitRef.current) {
        isGitRef.current = false;
        setIsGit(false);
      }
      return;
    }
    const id = ++gitFetchIdRef.current;
    getGitInfo(currentProject.path)
      .then((info) => {
        if (id !== gitFetchIdRef.current) return;
        const next = info.is_git;
        if (next !== isGitRef.current) {
          isGitRef.current = next;
          setIsGit(next);
        }
      })
      .catch(() => {
        if (id !== gitFetchIdRef.current) return;
        if (isGitRef.current) {
          isGitRef.current = false;
          setIsGit(false);
        }
      });
  }, [currentProject?.path]);

  const visibleChangedFiles = useMemo(() => {
    const visible = new Set(agentChangedFiles);
    acceptedFiles.forEach((path) => visible.delete(path));
    return visible;
  }, [acceptedFiles, agentChangedFiles]);

  const trafficSafe = isMacosDesktop() && workspaceExpandedLayout && !sidebarOpen;

  return (
    <Flex
      className={`app-shell ${sidebarOpen ? "sidebar-visible" : "sidebar-collapsed"}${
        workspacePanelOpen ? " workspace-open" : ""
      }${workspaceExpandedLayout ? " workspace-expanded" : ""}${
        fullscreen ? " fullscreen" : ""
      }${trafficSafe ? " traffic-safe" : ""}`}
    >
      <Flex direction="column" className={`left-panel${!sidebarOpen ? " collapsed" : ""}`}>
        <TitleBar
          collapsed={!sidebarOpen}
          onToggleCollapse={() => setSidebarOpen((value) => !value)}
          onOpenSearch={() => setSearchOpen(true)}
          fullscreen={fullscreen}
        />
        <SessionList
          sessions={sessions}
          projects={projects}
          selectedId={selectedId}
          selectedProjectId={selectedProjectId}
          workingSessionIds={streamingSessions}
          collapsed={!sidebarOpen}
          onSelect={handleSelectSession}
          onNew={handleNewSession}
          onSelectProject={handleSelectProject}
          onNewProject={() => {
            setEditingProject(null);
            setProjectOpen(true);
          }}
          onNewConversationInProject={handleNewSession}
          onRenameProject={handleEditProject}
          onDeleteProject={handleDeleteProject}
          onRename={handleRename}
          onDelete={handleDelete}
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenTasks={() => openView("tasks")}
          onOpenSkills={() => openView("skills")}
          onRefreshProjects={refreshProjects}
          activeView={tasksOpen ? "tasks" : skillsOpen ? "skills" : "chat"}
        />
      </Flex>
      <Flex direction="column" className="main-area">
        {/* 未配置 API Key：提示安装免费本地模型 */}
        {noUsableModel && !apiKeyBannerDismissed && (
          <div className="api-key-banner">
            <span className="api-key-banner-text">
              {t(
                "chat.noApiKeyBanner",
                "未配置 API Key，当前为演示模式。可安装免费本地模型离线使用，或配置 API Key。",
              )}
            </span>
            <Button
              size="small"
              variant="primary"
              onClick={() => {
                setSettingsInitialSection("local");
                setSettingsOpen(true);
              }}
            >
              {t("chat.installLocalModel", "去安装本地模型")}
            </Button>
            <Button
              variant="icon"
              size="small"
              className="api-key-banner-close"
              aria-label={t("common.close", "关闭")}
              title={t("common.close", "关闭")}
              onClick={() => setApiKeyBannerDismissed(true)}
            >
              <X size={14} />
            </Button>
          </div>
        )}
        {tasksOpen ? (
          <ScheduledTasksPage onOpenSidebar={() => setSidebarOpen(true)} />
        ) : skillsOpen ? (
          <SkillsPage onOpenSidebar={() => setSidebarOpen(true)} />
        ) : (
          <ChatStreamContext.Provider value={chatStreamValue}>
            <ChatHeader
              session={currentSession}
              project={currentProject}
              onOpenSidebar={() => setSidebarOpen(true)}
              onRename={handleRename}
              workspaceOpen={workspacePanelOpen}
              onToggleWorkspace={() => setWorkspacePanelOpen((open) => !open)}
              onPreviewFile={handlePreviewFile}
              isGit={isGit}
              tokenUsage={sessionTokenUsage}
            />
            {!selectedId ? (
              <NewChatGuide
                projectName={currentProject?.name ?? null}
                projectPath={currentProject?.path ?? null}
                cardsVisible={guideCardsVisible}
                disabled={!selectedProjectId}
                onAction={handleGuideAction}
              />
            ) : (
              <MessageList
                messages={messages}
                streaming={streaming}
                sessionId={selectedId}
                username={settings?.username || t("common.user", "用户")}
                workspacePath={currentProject?.path ?? null}
                onPreviewFile={handlePreviewFile}
                onRetryCloud={handleRetryCloud}
                hasMoreOlder={hasMoreOlder}
                loadingOlder={loadingOlder}
                onLoadOlder={loadOlderMessages}
              />
            )}
            <ChatInput
              key={composerKey}
              ref={composerRef}
              disabled={!selectedProjectId}
              streaming={streaming}
              onSupplement={handleSupplement}
              approvalMode={approvalMode}
              onApprovalModeChange={handleApprovalModeChange}
              effort={composerEffort}
              onEffortChange={(value) => {
                setComposerEffort(value);
                setSessionEffort(selectedId, value);
              }}
              models={switcherModels}
              modelId={composerModelId}
              onModelChange={handleModelChange}
              sessionId={selectedId}
              contextRefreshKey={contextRefreshKey}
              onValueChange={handleGuideValueChange}
              prefill={prefill}
              onPrefillConsumed={() => setPrefill(null)}
              projectPicker={
                !selectedId ? (
                  <div className="new-chat-project-bar">
                    <ProjectPicker
                      projects={projects}
                      currentProject={currentProject}
                      onSelect={(id) => handleNewSession(id)}
                      onNewProject={() => {
                        setEditingProject(null);
                        setProjectOpen(true);
                      }}
                    />
                  </div>
                ) : undefined
              }
              onSend={(question, files, mentions) =>
                void sendMessage(question, files, mentions, composerEffort)
              }
              onStop={handleStopStreaming}
              onPreviewFile={handlePreviewFile}
            />
          </ChatStreamContext.Provider>
        )}
      </Flex>
      <FilePreviewPanel
        open={workspacePanelOpen}
        repoPath={currentProject?.path ?? ""}
        selectedFile={previewFile}
        changedFiles={visibleChangedFiles}
        width={workspacePanelWidth}
        onWidthChange={setWorkspacePanelWidth}
        treeWidth={workspaceTreeWidth}
        onTreeWidthChange={setWorkspaceTreeWidth}
        expanded={workspaceExpanded}
        onToggleExpand={handleToggleWorkspaceExpand}
        noTransition={workspaceExpandTransitioning}
        onClose={() => setWorkspacePanelOpen(false)}
        onSelectFile={setPreviewFile}
        onAcceptFile={handleAcceptFile}
      />
      <SessionSearchModal
        open={searchOpen}
        sessions={sessions}
        selectedId={selectedId}
        projectId={selectedProjectId}
        onClose={() => setSearchOpen(false)}
        onSelect={handleSelectSession}
      />
      <ProjectModal
        open={projectOpen}
        project={editingProject}
        onClose={() => {
          setProjectOpen(false);
          setEditingProject(null);
        }}
        onSave={handleSaveProject}
      />
      {settingsOpen && settings && (
        <SettingsModal
          settings={settings}
          initialSection={settingsInitialSection}
          onClose={() => {
            setSettingsOpen(false);
            // 刷新模型列表：本地模型启动/停止后，切换器随之出现/消失
            void getSettings().then((current) => setSettings(current));
          }}
          onSave={(body) => void handleSettingsSave(body)}
          onSilentSave={(body) => void handleSilentSave(body)}
          onConfirm={(title, description, action) =>
            setConfirmState({ title, description, action })
          }
        />
      )}
      {confirmState && (
        <ConfirmDialog
          title={confirmState.title}
          description={confirmState.description}
          onConfirm={() => {
            // 先关闭确认弹窗再执行动作；动作内部的 setConfirmState(null) 是幂等空操作
            setConfirmState(null);
            void confirmState.action();
          }}
          onCancel={() => setConfirmState(null)}
        />
      )}
    </Flex>
  );
}
