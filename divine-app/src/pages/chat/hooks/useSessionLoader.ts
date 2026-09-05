// Session loading / pagination / changed-file tracking logic extracted
// from pages/chat/index.tsx to keep ChatPage focused on composition.
import { useCallback, useEffect, useRef, useState } from "react";
import { getSession, listSessions, messagesToChatMessages } from "@/services/api";
import { storageGetRaw } from "@/services/storage";
import { changedFilePathsFromResult, changedFileRel } from "@/pages/chat/chatUtils";
import type { ApprovalMode, ChatMessage, Project, Session } from "@/types";

interface SessionLoaderDeps {
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
  setSelectedProjectId: (id: string | null) => void;
  setSessions: (sessions: Session[]) => void;
  setSessionMessages: (
    sessionId: string | null,
    messages: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[]),
  ) => void;
  getCachedSessionMessages: (sessionId: string | null) => ChatMessage[] | undefined;
  setApprovalMode: (mode: ApprovalMode) => void;
  setWorkspaceExpanded: (value: boolean) => void;
  setWorkspaceExpandedLayout: (value: boolean) => void;
  workspacePanelOpen: boolean;
  projects: Project[];
}

export function useSessionLoader({
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
}: SessionLoaderDeps) {
  const [hasMoreOlder, setHasMoreOlder] = useState(false);
  const [oldestMessageId, setOldestMessageId] = useState<string | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [agentChangedFiles, setAgentChangedFiles] = useState<Set<string>>(new Set());
  // 会话切换序号：快速连点时丢弃过期的 loadSession fetch 结果
  const loadSessionSeqRef = useRef(0);
  const projectPathsRef = useRef<Record<string, string>>({});

  useEffect(() => {
    projectPathsRef.current = Object.fromEntries(
      projects.map((project) => [project.id, project.path]),
    );
  }, [projects]);

  const refreshSessions = useCallback(
    async (projectId?: string | null) => {
      const data = await listSessions();
      setSessions(data.sessions);
      return projectId
        ? data.sessions.filter((session) => session.project_id === projectId)
        : data.sessions;
    },
    [setSessions],
  );

  const loadSession = useCallback(
    async (id: string) => {
      const cached = getCachedSessionMessages(id);
      const hasCache = !!cached && cached.length > 0;
      // 有缓存：立即切换视图（消息即时显示），元信息由下方 fetch 补齐；
      // 无缓存：等 fetch 完成再切换（保持原有行为）。
      const seq = ++loadSessionSeqRef.current;
      if (hasCache) {
        setSelectedId(id);
      }
      const savedExpanded = storageGetRaw(`divine:workspace-expanded:${id}`) === "1";
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
          messagesToChatMessages(data.messages, data.tool_runs ?? [], data.todos),
        );
        setSelectedId(id);
      } else {
        // 有缓存：保留缓存消息（含流式），但把 API 返回的 choice_state 合并进去，
        // 使选项卡片的已选状态（DB 持久化）在刷新/重开会话后仍能恢复。
        const fresh = new Map(
          messagesToChatMessages(data.messages, data.tool_runs ?? [], data.todos).map((m) => [
            m.id,
            m,
          ]),
        );
        setSessionMessages(id, (prev) =>
          (prev || []).map((m) => {
            const apiMsg = fresh.get(m.id);
            return apiMsg?.choice_state ? { ...m, choice_state: apiMsg.choice_state } : m;
          }),
        );
      }
      setHasMoreOlder(Boolean(data.has_more));
      setOldestMessageId(data.messages.length > 0 ? data.messages[0].id : null);
      setLoadingOlder(false);
    },
    [
      getCachedSessionMessages,
      setApprovalMode,
      setSelectedId,
      setSelectedProjectId,
      setSessionMessages,
      setWorkspaceExpanded,
      setWorkspaceExpandedLayout,
    ],
  );

  const loadOlderMessages = useCallback(async () => {
    if (!selectedId || !oldestMessageId || loadingOlder || !hasMoreOlder) {
      return;
    }
    setLoadingOlder(true);
    try {
      const data = await getSession(selectedId, {
        limit: 80,
        beforeId: oldestMessageId,
      });
      const older = messagesToChatMessages(data.messages, data.tool_runs ?? [], data.todos);
      setSessionMessages(selectedId, (prev) => [...older, ...prev]);
      setHasMoreOlder(Boolean(data.has_more));
      if (data.messages.length > 0) {
        setOldestMessageId(data.messages[0].id);
      }
    } catch {
      // keep current list and allow retry on next scroll
    } finally {
      setLoadingOlder(false);
    }
  }, [hasMoreOlder, loadingOlder, oldestMessageId, selectedId, setSessionMessages]);

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

  // 工作区面板打开且会话就绪时，重算该会话的变更文件集合。
  useEffect(() => {
    if (!workspacePanelOpen || !selectedId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 面板打开/会话就绪时异步取变更文件，setState 在 await 之后
    void loadChangedFiles(selectedId);
  }, [loadChangedFiles, selectedId, workspacePanelOpen]);

  return {
    refreshSessions,
    loadSession,
    loadOlderMessages,
    loadChangedFiles,
    hasMoreOlder,
    setHasMoreOlder,
    oldestMessageId,
    setOldestMessageId,
    setLoadingOlder,
    loadingOlder,
    agentChangedFiles,
    setAgentChangedFiles,
  };
}
