// 应用启动恢复与会话偏好同步：自 ChatPage 拆出的启动链路。

import { useEffect, useRef } from "react";
import type { TFunction } from "i18next";
import { readLastSessionSelection } from "@/pages/chat/state/sessionStore";
import { defaultComposerEffort, getSessionEffort } from "@/pages/chat/state/sessionEffort";
import { getSessionModelId, resolveModelTargetId } from "@/pages/chat/state/sessionModel";
import { expandModelId } from "@/config/providers";
import { getSettings } from "@/services/api";
import type { Project, Session, Settings } from "@/types";

// getSettings 失败（sidecar 尚未就绪等）时的兜底设置：演示模式可交互，
// 避免白屏或 undefined 崩溃。
export function fallbackSettings(username: string): Settings {
  return {
    provider: "mock",
    base_url: "",
    model: "deepseek-flash",
    has_api_key: false,
    has_glm_key: false,
    workspace_dir: "",
    username,
    think_default: false,
    reasoning_effort: "high",
    context_limit: 30,
    global_shortcut_enabled: true,
    tools: [],
    models: [
      {
        id: "default",
        name: "DeepSeek V4 Flash",
        provider: "mock",
        model: "deepseek-flash",
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
  };
}

interface UseAppBootstrapOptions {
  refreshProjects: () => Promise<Project[]>;
  refreshSessions: (projectId?: string | null) => Promise<Session[]>;
  loadSession: (id: string) => Promise<void>;
  setSettings: (settings: Settings) => void;
  setComposerEffort: (effort: string) => void;
  setSelectedProjectId: (id: string | null) => void;
  setSelectedId: (id: string | null) => void;
  setSelectionReady: (ready: boolean) => void;
  t: TFunction;
}

/** 启动恢复链：设置 + 项目 + 会话列表加载，按上次选中恢复项目/会话。 */
export function useAppBootstrap(options: UseAppBootstrapOptions): void {
  const {
    refreshProjects,
    refreshSessions,
    loadSession,
    setSettings,
    setComposerEffort,
    setSelectedProjectId,
    setSelectedId,
    setSelectionReady,
    t,
  } = options;

  useEffect(() => {
    let cancelled = false;
    const savedSelection = readLastSessionSelection();

    Promise.all([refreshProjects(), getSettings()])
      .then(async ([projectList, currentSettings]) => {
        if (cancelled) return;
        setSettings(currentSettings);
        setComposerEffort(defaultComposerEffort(currentSettings));
        const sessionList = await refreshSessions();
        if (cancelled) return;
        const savedSession =
          sessionList.find((session) => session.id === savedSelection.sessionId) ?? null;
        const preferredProjectId = savedSession?.project_id ?? savedSelection.projectId;
        const initialProject =
          projectList.find((project) => project.id === preferredProjectId) ??
          projectList.find((project) => project.id === savedSession?.project_id) ??
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
              session.id === savedSelection.sessionId && session.project_id === initialProject.id,
          ) ??
          sessionList.find((session) => session.project_id === initialProject.id) ??
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
        setSettings(fallbackSettings(t("common.user", "用户")));
        setSelectionReady(true);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadSession, refreshProjects, refreshSessions, t]);
}

interface UseSessionPreferenceSyncOptions {
  selectedId: string | null;
  settings: Settings | null;
  setComposerEffort: (effort: string) => void;
  setComposerModelId: (id: string | null) => void;
}

/** 切换会话时恢复该会话记住的深度思考档位与模型；无记忆回落全局默认，
 * 记住/默认条目未配置 API Key 时回落到第一个已配置 Key 的提供商。 */
export function useSessionPreferenceSync(options: UseSessionPreferenceSyncOptions): void {
  const { selectedId, settings, setComposerEffort, setComposerModelId } = options;
  const prevEffortSessionRef = useRef<string | null>(null);
  const prevModelSessionRef = useRef<string | null>(null);

  useEffect(() => {
    if (selectedId === prevEffortSessionRef.current) return;
    prevEffortSessionRef.current = selectedId;
    if (!selectedId) return;
    const saved = getSessionEffort(selectedId);
    const valid = saved === "off" || saved === "low" || saved === "high" || saved === "max";
    setComposerEffort(valid ? saved : defaultComposerEffort(settings));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, settings]);

  useEffect(() => {
    if (selectedId === prevModelSessionRef.current) return;
    prevModelSessionRef.current = selectedId;
    const list = settings?.models ?? [];
    const activeId = list.find((entry) => entry.active)?.id ?? null;
    const remembered = selectedId ? getSessionModelId(selectedId) : null;
    setComposerModelId(expandModelId(resolveModelTargetId(list, remembered, activeId), list));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, settings]);
}
