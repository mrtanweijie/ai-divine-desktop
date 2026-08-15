import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import {
  cancelSessionGeneration,
  createProject,
  deleteProject,
  deleteSession,
  getSession,
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
import type { ApprovalMode, PreviewFile, Project, Settings } from "@/types";
import { useConfigState } from "@/pages/chat/state/configStore";
import { useFullscreen } from "@/pages/chat/state/fullscreenStore";
import { useInputState } from "@/pages/chat/state/inputStore";
import { useMessageState } from "@/pages/chat/state/messageStore";
import {
  readLastSessionSelection,
  useSessionState,
  writeLastSessionSelection,
} from "@/pages/chat/state/sessionStore";
import { Flex } from "@/components/ui/Flex";
import { TitleBar } from "@/components/TitleBar";
import { SessionSearchModal } from "@/pages/chat/components/SessionList/SessionSearchModal";
import { ProjectModal } from "@/pages/chat/components/ProjectModal";
import { ProjectPicker } from "@/pages/chat/components/ProjectPicker";
import { useChatStream } from "@/pages/chat/hooks/useChatStream";
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
  const [searchParams, setSearchParams] = useSearchParams();
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
  const [thinkEnabled, setThinkEnabled] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState("high");
  const [guideCardsVisible, setGuideCardsVisible] = useState(true);
  const [prefill, setPrefill] = useState<{
    text: string;
    nonce: number;
  } | null>(null);
  const [previewFile, setPreviewFile] = useState<PreviewFile | null>(null);
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
    const data = await getSession(id, { limit: 80 });
    let savedExpanded = false;
    try {
      savedExpanded =
        localStorage.getItem(`divine:workspace-expanded:${id}`) === "1";
    } catch {
      savedExpanded = false;
    }
    setWorkspaceExpanded(savedExpanded);
    setWorkspaceExpandedLayout(savedExpanded);
    setSelectedId(id);
    setSelectedProjectId(data.session.project_id);
    setApprovalMode(data.session.approval_mode ?? "ask");
    setMessages(
      messagesToChatMessages(data.messages, data.tool_runs ?? [], data.todos)
    );
    setHasMoreOlder(Boolean(data.has_more));
    setOldestMessageId(data.messages.length > 0 ? data.messages[0].id : null);
    setLoadingOlder(false);
  }, []);

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
      setMessages((prev) => [...older, ...prev]);
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
        setThinkEnabled(Boolean(currentSettings.think_default));
        setReasoningEffort(currentSettings.reasoning_effort ?? "high");
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
          setMessages([]);
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
          context_limit: 20,
          tools: [],
        });
        setSelectionReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [loadSession, refreshProjects, refreshSessions, t]);

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
          const next = !thinkEnabled;
          setThinkEnabled(next);
          setSettings({ ...settings, think_default: next });
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
      setThinkEnabled(settings?.think_default ?? false);
      setReasoningEffort(settings?.reasoning_effort ?? "high");
      setSelectedId(null);
      setMessages([]);
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
      if (streaming) return;
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
        setMessages([]);
      }
      closeSidebarForNarrow();
    },
    [
      closeSidebarForNarrow,
      loadSession,
      refreshSessions,
      setSearchParams,
      streaming,
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
      setMessages([]);
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
                setMessages([]);
              }
            } else {
              setGuideCardsVisible(true);
              setSelectedId(null);
              setMessages([]);
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
      if (streaming) return;
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete("view");
        return next;
      });
      await loadSession(id);
      closeSidebarForNarrow();
    },
    [closeSidebarForNarrow, loadSession, setSearchParams, streaming]
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
          const remaining = await refreshSessions(selectedProjectId);
          if (id === selectedId) {
            if (remaining.length > 0) {
              await loadSession(remaining[0].id);
            } else {
              setGuideCardsVisible(true);
              setSelectedId(null);
              setMessages([]);
            }
          }
          setConfirmState(null);
        },
      });
    },
    [loadSession, refreshSessions, selectedId, selectedProjectId, t]
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

  const handleStopStreaming = useCallback(async () => {
    if (!selectedId) return;
    try {
      await cancelSessionGeneration(selectedId);
    } catch {
      // sidecar may already be gone; the stream will fail on its own
    }
  }, [selectedId]);


  const { sendMessage } = useChatStream({
    selectedId,
    selectedProjectId,
    projects,
    approvalMode,
    streaming,
    workspacePanelOpenRef,
    setSessions,
    setSelectedId,
    setMessages,
    setStreaming,
    setAgentChangedFiles,
    setHasMoreOlder,
    setOldestMessageId,
    refreshSessions,
    refreshProjects,
    refreshWorkspace,
    loadChangedFiles,
    t,
  });

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
          workingSessionId={streaming ? selectedId : null}
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
          activeView={tasksOpen ? "tasks" : skillsOpen ? "skills" : "chat"}
          model={settings?.model ?? ""}
        />
      </Flex>
      <Flex direction="column" className="main-area">
        {tasksOpen ? (
          <ScheduledTasksPage
            onOpenSidebar={() => setSidebarOpen(true)}
          />
        ) : skillsOpen ? (
          <SkillsPage
            onOpenSidebar={() => setSidebarOpen(true)}
          />
        ) : (
          <>
            <ChatHeader
              session={currentSession}
              project={currentProject}
              onOpenSidebar={() => setSidebarOpen(true)}
              onRename={handleRename}
              workspaceOpen={workspacePanelOpen}
              onToggleWorkspace={() =>
                setWorkspacePanelOpen((open) => !open)
              }
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
              think={thinkEnabled}
              onThinkChange={setThinkEnabled}
              reasoningEffort={reasoningEffort}
              onReasoningEffortChange={setReasoningEffort}
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
                void sendMessage(
                  question,
                  files,
                  thinkEnabled,
                  reasoningEffort
                )
              }
              onStop={handleStopStreaming}
              onPreviewFile={handlePreviewFile}
            />
          </>
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
