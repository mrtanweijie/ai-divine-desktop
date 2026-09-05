// Workspace panel state machine extracted from pages/chat/index.tsx:
// open/width/expand/layout + localStorage persistence + resize handling.
import { useCallback, useEffect, useState } from "react";
import { isTauri, unwatchWorkspace, watchWorkspace } from "@/services/tauri";
import { storageGet, storageGetRaw, storageSetRaw } from "@/services/storage";
import { acceptedFilesKey, expandedWorkspaceWidth } from "@/pages/chat/chatUtils";
import type { Project, PreviewFile } from "@/types";

export function useWorkspacePanel({
  selectedId,
  currentProject,
  sidebarOpen,
}: {
  selectedId: string | null;
  currentProject: Project | null;
  sidebarOpen: boolean;
}) {
  const [previewFile, setPreviewFile] = useState<PreviewFile | null>(null);
  const [workspacePanelOpen, setWorkspacePanelOpen] = useState(false);
  const [workspacePanelWidth, setWorkspacePanelWidth] = useState(420);
  const [normalWorkspacePanelWidth, setNormalWorkspacePanelWidth] = useState(420);
  const [workspaceExpanded, setWorkspaceExpanded] = useState(false);
  const [workspaceExpandedLayout, setWorkspaceExpandedLayout] = useState(false);
  const [workspaceExpandTransitioning, setWorkspaceExpandTransitioning] = useState(false);
  const [workspaceTreeWidth, setWorkspaceTreeWidth] = useState(172);
  const [acceptedFiles, setAcceptedFiles] = useState<Set<string>>(new Set());

  const handlePreviewFile = useCallback((file: PreviewFile) => {
    setPreviewFile(file);
    setWorkspacePanelOpen(true);
  }, []);

  const handleToggleWorkspaceExpand = useCallback(() => {
    setWorkspaceExpandTransitioning(true);
    if (workspaceExpanded) {
      setWorkspacePanelWidth(normalWorkspacePanelWidth);
      setWorkspaceExpanded(false);
      setWorkspaceExpandedLayout(false);
      if (selectedId) {
        storageSetRaw(`divine:workspace-expanded:${selectedId}`, "0");
      }
    } else {
      setNormalWorkspacePanelWidth(workspacePanelWidth);

      setWorkspacePanelWidth(expandedWorkspaceWidth(sidebarOpen ? 244 : 0));
      setWorkspaceExpanded(true);
      setWorkspaceExpandedLayout(true);
      if (selectedId) {
        storageSetRaw(`divine:workspace-expanded:${selectedId}`, "1");
      }
    }
    window.setTimeout(() => setWorkspaceExpandTransitioning(false), 220);
  }, [normalWorkspacePanelWidth, selectedId, sidebarOpen, workspaceExpanded, workspacePanelWidth]);

  // 项目切换：重置预览/接受状态、恢复面板开关与已接受文件、监听工作区。
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 项目切换：同步重置预览状态并从 storage 恢复面板开关（外部存储同步）
    setPreviewFile(null);
    const saved = currentProject?.path
      ? storageGetRaw(`divine:workspace-panel-open:${currentProject.path}`)
      : null;
    setWorkspacePanelOpen(saved === "1");
    setAcceptedFiles(
      currentProject?.path
        ? new Set(storageGet<string[]>(acceptedFilesKey(currentProject.path), []))
        : new Set(),
    );
    if (!isTauri() || !currentProject?.path) return;
    void watchWorkspace(currentProject.path).catch(() => undefined);
    return () => {
      void unwatchWorkspace(currentProject.path).catch(() => undefined);
    };
  }, [currentProject?.path]);

  // 面板开关状态持久化（按项目路径）。
  useEffect(() => {
    if (!currentProject?.path) return;
    storageSetRaw(
      `divine:workspace-panel-open:${currentProject.path}`,
      workspacePanelOpen ? "1" : "0",
    );
  }, [currentProject?.path, workspacePanelOpen]);

  // 窗口尺寸变化时按比例调整面板宽度（保持可用最小宽度 320）。
  useEffect(() => {
    if (!workspacePanelOpen) return;
    const updateWidth = () => {
      const leftWidth = sidebarOpen ? 244 : 0;
      setWorkspacePanelWidth((prev) => {
        const available = Math.max(320, window.innerWidth - leftWidth - 900 - 48);
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

  // 展开态下侧栏开合变化时固定展开宽度。
  useEffect(() => {
    if (!workspacePanelOpen || !workspaceExpandedLayout) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 布局联动：面板开合/侧栏变化时同步派生宽度
    setWorkspacePanelWidth(expandedWorkspaceWidth(sidebarOpen ? 244 : 0));
  }, [sidebarOpen, workspaceExpandedLayout, workspacePanelOpen]);

  return {
    previewFile,
    setPreviewFile,
    workspacePanelOpen,
    setWorkspacePanelOpen,
    workspacePanelWidth,
    setWorkspacePanelWidth,
    normalWorkspacePanelWidth,
    setNormalWorkspacePanelWidth,
    workspaceExpanded,
    setWorkspaceExpanded,
    workspaceExpandedLayout,
    setWorkspaceExpandedLayout,
    workspaceExpandTransitioning,
    setWorkspaceExpandTransitioning,
    workspaceTreeWidth,
    setWorkspaceTreeWidth,
    acceptedFiles,
    setAcceptedFiles,
    handlePreviewFile,
    handleToggleWorkspaceExpand,
  };
}
