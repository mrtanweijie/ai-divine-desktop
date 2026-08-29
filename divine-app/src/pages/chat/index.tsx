import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import {
  createProject,
  deleteProject,
  deleteSession,
  getSession,
  getGitInfo,
  getSettings,
  getWorkspace,
  listProjects,
  listSessions,
  messagesToChatMessages,
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
import {
  isMacosDesktop,
  isTauri,
  unwatchWorkspace,
  watchWorkspace,
} from "@/services/tauri";
import type {
  ApprovalMode,
  ChatFile,
  PreviewFile,
  Project,
  SettingsSaveBody,
} from "@/types";
import { useConfigState } from "@/pages/chat/state/configStore";
import { useFullscreen } from "@/pages/chat/state/fullscreenStore";
import { useInputState } from "@/pages/chat/state/inputStore";
import { useMessageState } from "@/pages/chat/state/messageStore";
import {
  readLastSessionSelection,
  useSessionState,
  writeLastSessionSelection,
} from "@/pages/chat/state/sessionStore";
import {
  getSessionEffort,
  setSessionEffort,
} from "@/pages/chat/state/sessionEffort";
import {
  getSessionModelId,
  setSessionModelId,
} from "@/pages/chat/state/sessionModel";
import { Flex } from "@/components/ui/Flex";
import { TitleBar } from "@/components/TitleBar";
import { SessionSearchModal } from "@/pages/chat/components/SessionList/SessionSearchModal";
import { ProjectModal } from "@/pages/chat/components/ProjectModal";
import { ProjectPicker } from "@/pages/chat/components/ProjectPicker";
import { useChatStream } from "@/pages/chat/hooks/useChatStream";
import { ChatStreamContext } from "@/pages/chat/hooks/ChatStreamContext";
import {
  expandModelId,
  expandModelsForSwitcher,
} from "@/config/providers";
import "./index.less";
import {
  acceptedFilesKey,
  changedFilePathsFromResult,
  changedFileRel,
  expandedWorkspaceWidth,
} from "@/pages/chat/chatUtils";

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
  const messages = selectedId ? (messagesBySession[selectedId] ?? []) : [];

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
  // After a stream finishes, refresh the composer context ring usage.
  useEffect(() => {
    if (lastStreamingRef.current && !streaming) {
      setContextRefreshKey((key) => key + 1);
    }
    lastStreamingRef.current = streaming;
  }, [streaming]);
  const { settings, setSettings, setWorkspace } = useConfigState();
  // 只把已配置 API Key 的模型条目按提供商 list 展开，供对话框模型切换使用。
  // 未配置 Key 的提供商不会出现在切换列表里。
  const switcherModels = useMemo(
    () =>
      expandModelsForSwitcher(
        (settings?.models ?? []).filter((m) => m.has_api_key)
      ),
    [settings?.models]
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
  const openView = useCallback(
    (nextView: "tasks" | "skills") => {
      setWorkspacePanelOpen(false);
      setWorkspaceExpanded(false);
      setWorkspaceExpandedLayout(false);
      setSearchParams({ view: nextView });
    },
    [setSearchParams]
  );
  const [projectOpen, setProjectOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [composerKey, setComposerKey] = useState(0);
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("ask");
  const [composerEffort, setComposerEffort] = useState("off");
  const prevEffortSessionRef = useRef<string | null>(null);
  const [composerModelId, setComposerModelId] = useState<string | null>(null);
  const prevModelSessionRef = useRef<string | null>(null);
  // Bumped after each stream settles so the context ring refreshes usage.
  const [contextRefreshKey, setContextRefreshKey] = useState(0);
  const lastStreamingRef = useRef(false);
  const [guideCardsVisible, setGuideCardsVisible] = useState(true);
  const [prefill, setPrefill] = useState<{
    text: string;
    nonce: number;
  } | null>(null);
  const [previewFile, setPreviewFile] = useState<PreviewFile | null>(null);
  const [isGit, setIsGit] = useState(false);
  const [agentChangedFiles, setAgentChangedFiles] = useState<Set<string>>(
    new Set()
  );
  const [acceptedFiles, setAcceptedFiles] = useState<Set<string>>(new Set());
  const [workspacePanelOpen, setWorkspacePanelOpen] = useState(false);
  const [workspacePanelWidth, setWorkspacePanelWidth] = useState(420);
  const [normalWorkspacePanelWidth, setNormalWorkspacePanelWidth] =
    useState(420);
  const [workspaceExpanded, setWorkspaceExpanded] = useState(false);
  const [workspaceExpandedLayout, setWorkspaceExpandedLayout] =
    useState(false);
  const [workspaceExpandTransitioning, setWorkspaceExpandTransitioning] =
    useState(false);
  const [selectionReady, setSelectionReady] = useState(false);
  const [workspaceTreeWidth, setWorkspaceTreeWidth] = useState(172);
  const [hasMoreOlder, setHasMoreOlder] = useState(false);
  const [oldestMessageId, setOldestMessageId] = useState<string | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const projectPathsRef = useRef<Record<string, string>>({});
  // 会话切换序号：快速连点时丢弃过期的 loadSession fetch 结果
  const loadSessionSeqRef = useRef(0);
  const workspacePanelOpenRef = useRef(workspacePanelOpen);

  useEffect(() => {
    projectPathsRef.current = Object.fromEntries(
      projects.map((project) => [project.id, project.path])
    );
  }, [projects]);

  useEffect(() => {
    workspacePanelOpenRef.current = workspacePanelOpen;
  }, [workspacePanelOpen]);

  const refreshProjects = useCallback(async () => {
    const data = await listProjects();
    setProjects(data.projects);
    return data.projects;
  }, []);

  const refreshSessions = useCallback(async (projectId?: string | null) => {
    const data = await listSessions();
    setSessions(data.sessions);
    return projectId
      ? data.sessions.filter((session) => session.project_id === projectId)
      : data.sessions;
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
    const cached = getCachedSessionMessages(id);
    const hasCache = !!cached && cached.length > 0;
    // 有缓存：立即切换视图（消息即时显示），元信息由下方 fetch 补齐；
    // 无缓存：等 fetch 完成再切换（保持原有行为）。
    const seq = ++loadSessionSeqRef.current;
    if (hasCache) {
      setSelectedId(id);
    }
    let savedExpanded = false;
    try {
      savedExpanded =
        localStorage.getItem(`divine:workspace-expanded:${id}`) === "1";
    } catch {
      savedExpanded = false;
    }
    setWorkspaceExpanded(savedExpanded);
    setWorkspaceExpandedLayout(savedExpanded);

    const data = await getSession(id, { limit: 80 });
    // 已被更新的点击取代时丢弃本次结果，避免旧请求覆盖新会话的元信息。
    if (seq !== loadSessionSeqRef.current) return;
    setSelectedProjectId(data.session.project_id);
    setApprovalMode(data.session.approval_mode ?? "ask");
    if (!hasCache) {
      setSessionMessages(
        id,
        messagesToChatMessages(
          data.messages,
          data.tool_runs ?? [],
          data.todos
        )
      );
      setSelectedId(id);
    } else {
      // 有缓存：保留缓存消息（含流式），但把 API 返回的 choice_state 合并进去，
      // 使选项卡片的已选状态（DB 持久化）在刷新/重开会话后仍能恢复。
      const fresh = new Map(
        messagesToChatMessages(data.messages, data.tool_runs ?? [], data.todos)
          .map((m) => [m.id, m])
      );
      setSessionMessages(id, (prev) =>
        (prev || []).map((m) => {
          const apiMsg = fresh.get(m.id);
          return apiMsg?.choice_state ? { ...m, choice_state: apiMsg.choice_state } : m;
        })
      );
    }
    setHasMoreOlder(Boolean(data.has_more));
    setOldestMessageId(data.messages.length > 0 ? data.messages[0].id : null);
    setLoadingOlder(false);
  }, [getCachedSessionMessages, setSessionMessages]);

  const loadOlderMessages = useCallback(async () => {
    if (
      !selectedId ||
      !oldestMessageId ||
      loadingOlder ||
      !hasMoreOlder
    ) {
      return;
    }
    setLoadingOlder(true);
    try {
      const data = await getSession(selectedId, {
        limit: 80,
        beforeId: oldestMessageId,
      });
      const older = messagesToChatMessages(
        data.messages,
        data.tool_runs ?? [],
        data.todos
      );
      setSessionMessages(
        selectedId,
        (prev) => [...older, ...prev]
      );
      setHasMoreOlder(Boolean(data.has_more));
      if (data.messages.length > 0) {
        setOldestMessageId(data.messages[0].id);
      }
    } catch {
      // keep current list and allow retry on next scroll
    } finally {
      setLoadingOlder(false);
    }
  }, [
    hasMoreOlder,
    loadingOlder,
    oldestMessageId,
    selectedId,
  ]);

  const loadChangedFiles = useCallback(async (id: string) => {
    if (!id) {
      setAgentChangedFiles(new Set());
      return;
    }
    try {
      const data = await getSession(id);
      const projectPath = data.session.project_id
        ? projectPathsRef.current[data.session.project_id]
        : null;
      const changedFiles = new Set<string>();
      if (projectPath) {
        for (const run of data.tool_runs ?? []) {
          if (run.status !== "done" || !run.output) continue;
          try {
            const result = JSON.parse(run.output) as unknown;
            for (const filePath of changedFilePathsFromResult(result)) {
              const rel = changedFileRel(projectPath, filePath);
              if (rel) changedFiles.add(rel);
            }
          } catch {
            // malformed tool output is not a file marker
          }
        }
      }
      setAgentChangedFiles(changedFiles);
    } catch {
      setAgentChangedFiles(new Set());
    }
  }, []);

  useEffect(() => {
    if (!workspacePanelOpen || !selectedId) return;
    void loadChangedFiles(selectedId);
  }, [loadChangedFiles, selectedId, workspacePanelOpen]);

  useEffect(() => {
    let cancelled = false;
    const savedSelection = readLastSessionSelection();

    Promise.all([refreshProjects(), getSettings()])
      .then(async ([projectList, currentSettings]) => {
        if (cancelled) return;
        setSettings(currentSettings);
        setComposerEffort(
          currentSettings.think_default
            ? currentSettings.reasoning_effort ?? "high"
            : "off"
        );
        const sessionList = await refreshSessions();
        if (cancelled) return;
        const savedSession =
          sessionList.find(
            (session) => session.id === savedSelection.sessionId
          ) ?? null;
        const preferredProjectId =
          savedSession?.project_id ?? savedSelection.projectId;
        const initialProject =
          projectList.find((project) => project.id === preferredProjectId) ??
          projectList.find(
            (project) => project.id === savedSession?.project_id
          ) ??
          projectList[0] ??
          null;
        if (!initialProject) {
          setSelectedProjectId(null);
          setSelectionReady(true);
          return;
        }
        setSelectedProjectId(initialProject.id);
        const initialSession =
          sessionList.find(
            (session) =>
              session.id === savedSelection.sessionId &&
              session.project_id === initialProject.id
          ) ??
          sessionList.find(
            (session) => session.project_id === initialProject.id
          ) ??
          null;
        if (initialSession) {
          await loadSession(initialSession.id);
        } else {
          setSelectedId(null);
        }
        setSelectionReady(true);
      })
      .catch(() => {
        if (cancelled) return;
        setSettings({
          provider: "mock",
          base_url: "",
          model: "deepseek-v4-flash",
          has_api_key: false,
          has_glm_key: false,
          workspace_dir: "",
          username: t("common.user", "用户"),
          think_default: false,
          reasoning_effort: "high",
          context_limit: 30,
          tools: [],
          models: [
            {
              id: "default",
              name: "DeepSeek V4 Flash",
              provider: "mock",
              model: "deepseek-v4-flash",
              base_url: "",
              has_api_key: false,
              active: true,
            },
          ],
          local_llm_enabled: false,
          local_llm_mode: "keyword",
          local_llm_port: 8016,
          local_llm_model: "",
          local_llm_ctx_size: 2048,
          local_llm_threshold: 0.75,
          installed_models: [],
        });
        setSelectionReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [loadSession, refreshProjects, refreshSessions, t]);

  // 切换会话时恢复该会话单独记住的深度思考档位；
  // 没有记忆的会话回落到全局默认。
  useEffect(() => {
    if (selectedId === prevEffortSessionRef.current) return;
    prevEffortSessionRef.current = selectedId;
    if (!selectedId) return;
    const saved = getSessionEffort(selectedId);
    const valid =
      saved === "off" || saved === "low" || saved === "high" || saved === "max";
    setComposerEffort(
      valid
        ? saved
        : settings?.think_default
          ? settings?.reasoning_effort ?? "high"
          : "off"
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, settings]);

  // 切换会话时恢复该会话记住的模型；没有记忆的会话回落到设置里的默认模型。
  // 若记住/默认的条目未配置 API Key，回退到第一个已配置 Key 的提供商。
  useEffect(() => {
    if (selectedId === prevModelSessionRef.current) return;
    prevModelSessionRef.current = selectedId;
    const activeId =
      settings?.models?.find((entry) => entry.active)?.id ?? null;
    const savedId = selectedId ? getSessionModelId(selectedId) : null;
    const rawId = savedId ?? activeId;
    const list = settings?.models ?? [];
    const baseId = rawId?.split("::")[0] ?? null;
    const entry = baseId ? list.find((m) => m.id === baseId) : undefined;
    const targetId =
      entry && entry.has_api_key
        ? rawId
        : (list.find((m) => m.has_api_key)?.id ?? null);
    setComposerModelId(expandModelId(targetId, list));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, settings]);

  useEffect(() => {
    if (!selectionReady) return;
    writeLastSessionSelection(selectedProjectId, selectedId);
  }, [selectedId, selectedProjectId, selectionReady]);

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

  useEffect(() => {
    if (!selectedId) {
      setGuideCardsVisible(true);
    }
  }, [selectedId]);

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
          const defaultEffort = settings.think_default
            ? settings.reasoning_effort ?? "high"
            : "off";
          const next =
            composerEffort === "off"
              ? defaultEffort === "off"
                ? "high"
                : defaultEffort
              : "off";
          setComposerEffort(next);
          setSessionEffort(selectedId, next);
          setSettings({ ...settings, think_default: next !== "off" });
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

  const handleNewSession = useCallback(
    (projectId?: string) => {
      // 多会话并发：点「新对话」不打断任何正在进行的流，
      // 只重置当前视图（messages 由 selectedId 派生，自动为空）。
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete("view");
        return next;
      });
      const safeProjectId =
        typeof projectId === "string" ? projectId : undefined;
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
      setComposerEffort(
        settings?.think_default
          ? settings?.reasoning_effort ?? "high"
          : "off"
      );
      setSelectedId(null);
      closeSidebarForNarrow();
      setTimeout(() => composerRef.current?.focus(), 0);
    },
    [
      closeSidebarForNarrow,
      projects,
      selectedId,
      selectedProjectId,
      setSearchParams,
      setSelectedProjectId,
      sessions,
      settings,
    ]
  );

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
      loadSession,
      refreshSessions,
      setSearchParams,
    ]
  );

  const handleSaveProject = useCallback(
    async (body: {
      name: string;
      path?: string;
      icon?: string;
    }) => {
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
    [closeSidebarForNarrow, editingProject, refreshProjects, refreshSessions]
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
          { name: project?.name ?? "", count: sessionCount }
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
      t,
    ]
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
    [closeSidebarForNarrow, loadSession, selectedId, setSearchParams, streaming]
  );

  const handleRename = useCallback(
    async (id: string, title: string) => {
      if (!title.trim()) return;
      await renameSession(id, title.trim());
      await refreshSessions(selectedProjectId);
    },
    [refreshSessions, selectedProjectId]
  );

  const handleDelete = useCallback(
    (id: string) => {
      setConfirmState({
        title: t("session.deleteTitle", "删除会话"),
        description: t(
          "session.deleteConfirm",
          "删除后该会话的消息和工具记录将无法恢复。"
        ),
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
      t,
    ]
  );

  const handleSettingsSave = useCallback(
    async (body: SettingsSaveBody) => {
      const updated = await updateSettings(body);
      setSettings(updated);
      // 设置里的默认思考档位变更后立即同步到输入框，无需新建会话。
      setComposerEffort(
        updated.think_default ? updated.reasoning_effort ?? "high" : "off"
      );
      // 默认模型变更后，若当前会话没有单独记忆的模型，立即跟随。
      // 若记住/默认的条目未配置 API Key，回退到第一个已配置 Key 的提供商。
      const activeId = updated.models?.find((entry) => entry.active)?.id ?? null;
      const remembered = selectedId ? getSessionModelId(selectedId) : null;
      const rawId = remembered ?? activeId;
      const list = updated.models ?? [];
      const baseId = rawId?.split("::")[0] ?? null;
      const entry = baseId ? list.find((m) => m.id === baseId) : undefined;
      const targetId =
        entry && entry.has_api_key
          ? rawId
          : (list.find((m) => m.has_api_key)?.id ?? null);
      setComposerModelId(expandModelId(targetId, list));
      setSettingsOpen(false);
      await refreshWorkspace();
    },
    [refreshWorkspace, selectedId]
  );

  // 静默保存（不关闭弹窗）：用于设为默认等即时生效的操作
  const handleSilentSave = useCallback(
    async (body: SettingsSaveBody) => {
      const updated = await updateSettings(body);
      setSettings(updated);
      const activeId = updated.models?.find((entry) => entry.active)?.id ?? null;
      const remembered = selectedId ? getSessionModelId(selectedId) : null;
      const rawId = remembered ?? activeId;
      const list = updated.models ?? [];
      const baseId = rawId?.split("::")[0] ?? null;
      const entry = baseId ? list.find((m) => m.id === baseId) : undefined;
      const targetId =
        entry && entry.has_api_key
          ? rawId
          : (list.find((m) => m.has_api_key)?.id ?? null);
      setComposerModelId(expandModelId(targetId, list));
    },
    [selectedId]
  );

  const handleModelChange = useCallback(
    (modelId: string) => {
      setComposerModelId(modelId);
      setSessionModelId(selectedId, modelId);
    },
    [selectedId]
  );

  const handleApprovalModeChange = useCallback(
    (mode: ApprovalMode) => {
      setApprovalMode(mode);
      if (selectedId) {
        void updateSessionApprovalMode(selectedId, mode).catch(() => undefined);
      }
    },
    [selectedId]
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

  const { sendMessage, stopStreaming, retryCloud } = useChatStream({
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

  // 本地模型回答的【重答】：用云端重答同一条问题（复用当前思考档位）。
  const handleRetryCloud = useCallback(
    (messageId: string) => {
      void retryCloud(messageId, composerEffort);
    },
    [composerEffort, retryCloud]
  );

  // 供消息渲染层的可点击组件（如风格选择卡片）发送消息。
  const chatStreamValue = useMemo(
    () => ({
      sendMessage: (
        question: string,
        files: ChatFile[] = [],
        effort?: string
      ) => {
        void sendMessage(question, files, effort ?? composerEffort);
      },
      effort: composerEffort,
    }),
    [sendMessage, composerEffort]
  );

  const currentSession = useMemo(
    () => sessions.find((session) => session.id === selectedId) ?? null,
    [selectedId, sessions]
  );

  const currentProject = useMemo(
    () =>
      projects.find(
        (project) =>
          project.id === (currentSession?.project_id ?? selectedProjectId)
      ) ?? null,
    [currentSession?.project_id, projects, selectedProjectId]
  );

  const handlePreviewFile = useCallback((file: PreviewFile) => {
    setPreviewFile(file);
    setWorkspacePanelOpen(true);
  }, []);

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
          try {
            localStorage.setItem(
              acceptedFilesKey(currentProject.path),
              JSON.stringify([...next])
            );
          } catch {
            // localStorage unavailable, accepted state stays in memory
          }
        }
        return next;
      });
    },
    [currentProject?.path]
  );

  const handleToggleWorkspaceExpand = useCallback(() => {
    setWorkspaceExpandTransitioning(true);
    if (workspaceExpanded) {
      setWorkspacePanelWidth(normalWorkspacePanelWidth);
      setWorkspaceExpanded(false);
      setWorkspaceExpandedLayout(false);
      if (selectedId) {
        try {
          localStorage.setItem(
            `divine:workspace-expanded:${selectedId}`,
            "0"
          );
        } catch {
          // localStorage unavailable, state stays in memory
        }
      }
    } else {
      setNormalWorkspacePanelWidth(workspacePanelWidth);
      setWorkspacePanelWidth(
        expandedWorkspaceWidth(sidebarOpen ? 244 : 0)
      );
      setWorkspaceExpanded(true);
      setWorkspaceExpandedLayout(true);
      if (selectedId) {
        try {
          localStorage.setItem(
            `divine:workspace-expanded:${selectedId}`,
            "1"
          );
        } catch {
          // localStorage unavailable, state stays in memory
        }
      }
    }
    window.setTimeout(
      () => setWorkspaceExpandTransitioning(false),
      220
    );
  }, [
    normalWorkspacePanelWidth,
    selectedId,
    workspaceExpanded,
    workspacePanelWidth,
  ]);

  useEffect(() => {
    setPreviewFile(null);
    setAgentChangedFiles(new Set());
    setHasMoreOlder(false);
    setOldestMessageId(null);
    setLoadingOlder(false);
    try {
      const saved = currentProject?.path
        ? localStorage.getItem(
            `divine:workspace-panel-open:${currentProject.path}`
          )
        : null;
      setWorkspacePanelOpen(saved === "1");
    } catch {
      setWorkspacePanelOpen(false);
    }
    try {
      setAcceptedFiles(
        currentProject?.path
          ? new Set(
              JSON.parse(
                localStorage.getItem(acceptedFilesKey(currentProject.path)) ??
                  "[]"
              ) as string[]
            )
          : new Set()
      );
    } catch {
      setAcceptedFiles(new Set());
    }
    if (!isTauri() || !currentProject?.path) return;
    void watchWorkspace(currentProject.path).catch(() => undefined);
    return () => {
      void unwatchWorkspace(currentProject.path).catch(() => undefined);
    };
  }, [currentProject?.path]);

  useEffect(() => {
    if (!currentProject?.path) return;
    try {
      localStorage.setItem(
        `divine:workspace-panel-open:${currentProject.path}`,
        workspacePanelOpen ? "1" : "0"
      );
    } catch {
      // localStorage unavailable, state stays in memory
    }
  }, [currentProject?.path, workspacePanelOpen]);

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

  const trafficSafe =
    isMacosDesktop() && workspaceExpandedLayout && !sidebarOpen;

  useEffect(() => {
    if (!workspacePanelOpen) return;
    const updateWidth = () => {
      const leftWidth = sidebarOpen ? 244 : 0;
      setWorkspacePanelWidth((prev) => {
        const available = Math.max(
          320,
          window.innerWidth - leftWidth - 900 - 48
        );
        if (workspaceExpandedLayout) {
          return expandedWorkspaceWidth(leftWidth);
        }
        const current = Math.max(320, Math.min(760, prev));
        const ratio = current / available;
        const next = Math.max(320, Math.min(760, ratio * available));
        return Math.round(next);
      });
    };
    window.addEventListener("resize", updateWidth);
    return () => window.removeEventListener("resize", updateWidth);
  }, [sidebarOpen, workspaceExpandedLayout, workspacePanelOpen]);

  useEffect(() => {
    if (!workspacePanelOpen || !workspaceExpandedLayout) return;
    setWorkspacePanelWidth(
      expandedWorkspaceWidth(sidebarOpen ? 244 : 0)
    );
  }, [sidebarOpen, workspaceExpandedLayout, workspacePanelOpen]);

  return (
    <Flex
      className={`app-shell ${sidebarOpen ? "sidebar-visible" : "sidebar-collapsed"}${
        workspacePanelOpen ? " workspace-open" : ""
      }${workspaceExpandedLayout ? " workspace-expanded" : ""}${
        fullscreen ? " fullscreen" : ""
      }${trafficSafe ? " traffic-safe" : ""}`}
    >
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
                "未配置 API Key，当前为演示模式。可安装免费本地模型离线使用，或配置 API Key。"
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
          <ScheduledTasksPage
            onOpenSidebar={() => setSidebarOpen(true)}
          />
        ) : skillsOpen ? (
          <SkillsPage
            onOpenSidebar={() => setSidebarOpen(true)}
          />
        ) : (
          <ChatStreamContext.Provider value={chatStreamValue}>
            <ChatHeader
              session={currentSession}
              project={currentProject}
              onOpenSidebar={() => setSidebarOpen(true)}
              onRename={handleRename}
              workspaceOpen={workspacePanelOpen}
              onToggleWorkspace={() =>
                setWorkspacePanelOpen((open) => !open)
              }
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
              disabled={streaming || !selectedProjectId}
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
              onSend={(question, files) =>
                void sendMessage(question, files, composerEffort)
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
