// 生成任务页（035 §9，交互对齐技能页）：统计行 + 筛选 chips + 三列任务卡片。
// 卡片：状态图标 + prompt + 参数 chips + 摘要 + 底部主操作；
// 播放在卡片内展开（展开时占满整行）。
import {
  AlertCircle,
  Clapperboard,
  FolderOpen,
  MoreHorizontal,
  PanelLeftOpen,
  Play,
  RotateCcw,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Dropdown, type DropdownItem } from "@/components/ui/Dropdown";
import { toast } from "@/components/ui/Toast";
import { VideoPlayer } from "@/components/VideoPlayer";
import { useMediaTasks } from "@/hooks/useMediaTasks";
import { dismissMediaTask, mediaStreamUrl, type MediaTask } from "@/services/mediaTasks";
import { isTauri, openFileLocation } from "@/services/tauri";
import "./index.less";

type MediaFilter = "all" | "running" | "done";

const API_BASE_URL = "/api";

/** 「另存为」：Tauri save 对话框选路径 → 服务端复制（无 fs 插件，走 API）。 */
async function saveTaskAs(task: MediaTask): Promise<void> {
  const { save } = await import("@tauri-apps/plugin-dialog");
  const name = task.file_path?.split("/").pop() ?? "video.mp4";
  const dest = await save({ defaultPath: name });
  if (!dest) return;
  const response = await fetch(`${API_BASE_URL}/media/tasks/${task.id}/save-as`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dest }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail ?? "保存失败");
  }
  toast.success("已保存");
}

function isRunning(task: MediaTask): boolean {
  return task.status === "queued" || task.status === "running";
}

function formatSince(task: MediaTask): string {
  const started = new Date(task.created_at).getTime();
  if (Number.isNaN(started)) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function paramChips(task: MediaTask): string[] {
  const params = task.params || {};
  const chips: string[] = [];
  if (params.duration) chips.push(`${params.duration}s`);
  if (params.resolution) chips.push(String(params.resolution));
  if (params.aspect_ratio) chips.push(String(params.aspect_ratio));
  if (params.mode === "first_frame") chips.push("图生视频");
  if (params.mode === "first_last") chips.push("首尾帧");
  if (params.source === "article") chips.push("资讯");
  return chips;
}

function statusLabel(task: MediaTask, t: (key: string, fallback: string) => string): string {
  if (task.status === "queued") return t("tool.videoTaskQueued", "已排队");
  if (task.status === "running") return t("tool.videoTaskRunningShort", "生成中");
  if (task.status === "succeeded") return t("tool.videoTaskStateDone", "已完成");
  if (task.status === "failed" || task.status === "expired")
    return t("tool.videoTaskStateFailed", "失败");
  return task.status;
}

function MediaTaskCard({
  task,
  onPlay,
  onShowReason,
  onDelete,
  onAct,
}: {
  task: MediaTask;
  onPlay: (task: MediaTask) => void;
  onShowReason: (task: MediaTask) => void;
  onDelete: (task: MediaTask) => void;
  onAct: (action: () => Promise<void>) => void;
}) {
  const { t } = useTranslation();
  const running = isRunning(task);
  const failed = task.status === "failed" || task.status === "expired";
  const succeeded = task.status === "succeeded" && Boolean(task.file_path);
  const chips = paramChips(task);
  const fileName = task.file_path?.split("/").pop() ?? "";
  const modelLabel = [task.provider, task.model].filter(Boolean).join(" · ");
  const state = running ? "running" : failed ? "failed" : "done";

  // 摘要只讲"现在有事没事"：跑着说等待、失败给原因、完成给文件名
  const summary = succeeded
    ? fileName
    : failed
      ? (task.error ?? statusLabel(task, t))
      : t("tool.mediaTaskWaiting", "云端生成中，完成后会自动出现在这里");

  const dismiss = () =>
    onAct(async () => {
      await dismissMediaTask(task.id);
      toast.success(t("tool.videoDismissedToast", "已不再等待；云端仍会跑完，稍后可以回来取"));
    });

  const retry = () =>
    onAct(async () => {
      const response = await fetch(`/api/media/tasks/${task.id}/retry`, { method: "POST" });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail ?? "重试失败");
      }
      toast.success(t("tool.videoRetryStarted", "已重新提交"));
    });

  // 操作全部收进三点菜单（2026-11-04 用户指定：右下角三点 + hover 展示）
  const items: DropdownItem[] = [];
  if (running) {
    items.push({
      key: "dismiss",
      label: t("tool.videoDismiss", "不再等待"),
      icon: <Clapperboard size={14} />,
      onClick: dismiss,
    });
  }
  if (succeeded) {
    items.push({
      key: "play",
      label: t("tool.videoTaskPlay", "播放"),
      icon: <Play size={14} />,
      onClick: () => onPlay(task),
    });
    if (isTauri()) {
      items.push({
        key: "reveal",
        label: t("tool.openDirectory", "打开所在目录"),
        icon: <FolderOpen size={14} />,
        onClick: () => void openFileLocation(task.file_path as string),
      });
      items.push({
        key: "save",
        label: t("tool.videoSaveAs", "另存为"),
        icon: <Save size={14} />,
        onClick: () => onAct(() => saveTaskAs(task)),
      });
    }
  }
  if (failed) {
    items.push({
      key: "reason",
      label: t("tool.videoTaskNoAction", "查看原因"),
      icon: <AlertCircle size={14} />,
      onClick: () => onShowReason(task),
    });
    items.push({
      key: "retry",
      label: t("tool.videoRetry", "重试"),
      icon: <RotateCcw size={14} />,
      onClick: retry,
    });
  }
  if (!running) {
    items.push({
      key: "delete",
      label: t("tool.videoDelete", "删除"),
      icon: <Trash2 size={14} />,
      danger: true,
      onClick: () => onDelete(task),
    });
  }

  return (
    <div className={`media-task-card is-${state}`}>
      <div className="media-task-top">
        <span className={`media-task-dot is-${state}`} aria-hidden />
        <span className="media-task-title" title={task.prompt}>
          {task.prompt || t("tool.mediaUnnamedTask", "未命名任务")}
        </span>
        <span className="media-task-time">
          {running ? formatSince(task) : statusLabel(task, t)}
        </span>
      </div>

      <div className="media-task-meta">
        {chips.map((chip, index) => (
          <span key={chip}>
            {index > 0 && <span className="media-task-meta-sep">·</span>}
            {chip}
          </span>
        ))}
        {modelLabel && (
          <span>
            {chips.length > 0 && <span className="media-task-meta-sep">·</span>}
            {modelLabel}
          </span>
        )}
      </div>

      <p
        className={`media-task-desc${failed ? " is-failed" : ""}`}
        title={failed ? summary : undefined}
      >
        {summary}
      </p>

      <div className="media-task-actions">
        <Dropdown
          align="end"
          direction="auto"
          openOn="both"
          trigger={
            <Button
              variant="icon"
              size="small"
              aria-label={t("tool.mediaMoreActions", "更多操作")}
              title={t("tool.mediaMoreActions", "更多操作")}
            >
              <MoreHorizontal size={15} />
            </Button>
          }
          items={items}
        />
      </div>
    </div>
  );
}

export function MediaTasksPage({ onOpenSidebar }: { onOpenSidebar?: () => void }) {
  const { t } = useTranslation();
  const { tasks } = useMediaTasks();
  const [filter, setFilter] = useState<MediaFilter>("all");
  const [showDismissed, setShowDismissed] = useState(false);
  const [playingTask, setPlayingTask] = useState<MediaTask | null>(null);
  const [reasonTask, setReasonTask] = useState<MediaTask | null>(null);
  const [deleteTask, setDeleteTask] = useState<MediaTask | null>(null);

  const running = useMemo(() => tasks.filter((task) => isRunning(task)), [tasks]);
  const done = useMemo(() => tasks.filter((task) => !isRunning(task)), [tasks]);
  const dismissedRunning = useMemo(
    () => running.filter((task) => (task.extras || {}).dismissed),
    [running],
  );

  const visible = useMemo(() => {
    let list = tasks;
    if (filter === "running") list = running;
    if (filter === "done") list = done;
    // 「不再等待」的任务默认隐藏，摘要行给入口
    if (!showDismissed) {
      list = list.filter((task) => !isRunning(task) || !(task.extras || {}).dismissed);
    }
    return [...list].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  }, [tasks, filter, running, done, showDismissed]);

  useEffect(() => {
    if (!playingTask) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPlayingTask(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [playingTask]);

  const onAct = useCallback(async (action: () => Promise<void>) => {
    try {
      await action();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  }, []);

  const openPlayer = useCallback((task: MediaTask) => {
    setPlayingTask(task);
  }, []);
  const openReason = useCallback((task: MediaTask) => {
    setReasonTask(task);
  }, []);
  const askDelete = useCallback((task: MediaTask) => {
    setDeleteTask(task);
  }, []);

  const confirmDelete = useCallback(() => {
    if (!deleteTask) return;
    const target = deleteTask;
    setDeleteTask(null);
    void onAct(async () => {
      const response = await fetch(`/api/media/tasks/${target.id}`, { method: "DELETE" });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail ?? "删除失败");
      }
      if (playingTask?.id === target.id) setPlayingTask(null);
      if (reasonTask?.id === target.id) setReasonTask(null);
    });
  }, [deleteTask, onAct, playingTask?.id, reasonTask?.id]);

  return (
    <div className="media-page">
      <div className="media-toolbar">
        <div className="media-toolbar-left">
          {onOpenSidebar && (
            <Button
              variant="icon"
              className="media-sidebar-button"
              onClick={onOpenSidebar}
              aria-label={t("common.expandSessionList", "展开会话列表")}
              title={t("session.list", "会话列表")}
            >
              <PanelLeftOpen size={15} />
            </Button>
          )}
          <div className="media-summary">
            <span>
              {t("tool.mediaSummaryTotal", "共 {{count}} 个任务", { count: tasks.length })}
            </span>
            <span className="media-summary-sep">·</span>
            <span>
              {t("tool.mediaSummaryRunning", "进行中 {{count}}", { count: running.length })}
            </span>
            <span className="media-summary-sep">·</span>
            <span>{t("tool.mediaSummaryDone", "已完成 {{count}}", { count: done.length })}</span>
          </div>
        </div>
        <div
          className="media-filter"
          role="group"
          aria-label={t("tool.mediaFilterLabel", "任务状态筛选")}
        >
          {(
            [
              ["all", t("tool.mediaFilterAll", "全部")],
              ["running", t("tool.mediaFilterRunning", "进行中")],
              ["done", t("tool.mediaFilterDone", "已完成")],
            ] as const
          ).map(([value, label]) => (
            <div
              key={value}
              role="tab"
              aria-selected={filter === value}
              tabIndex={0}
              className={`media-filter-item${filter === value ? " active" : ""}`}
              onClick={() => setFilter(value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setFilter(value);
                }
              }}
            >
              {label}
            </div>
          ))}
        </div>
      </div>

      <div className="media-body">
        {visible.length === 0 ? (
          <EmptyState
            icon={<Clapperboard size={22} />}
            title={t("tool.mediaEmptyTitle", "还没有生成任务")}
            description={t("tool.mediaEmptyAll", "在对话里让 AI 生成视频后会出现在这里")}
          />
        ) : (
          <div className="media-grid">
            {visible.map((task) => (
              <MediaTaskCard
                key={task.id}
                task={task}
                onPlay={openPlayer}
                onShowReason={openReason}
                onDelete={askDelete}
                onAct={onAct}
              />
            ))}
          </div>
        )}
        {dismissedRunning.length > 0 && (filter === "all" || filter === "running") && (
          <div
            role="button"
            tabIndex={0}
            className="media-dismissed-toggle"
            onClick={() => setShowDismissed((value) => !value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setShowDismissed((value) => !value);
              }
            }}
          >
            {showDismissed
              ? t("tool.mediaHideDismissed", "收起已不再等待的任务")
              : t("tool.mediaShowDismissed", "已隐藏 {{count}} 个（仍在生成）", {
                  count: dismissedRunning.length,
                })}
          </div>
        )}
      </div>

      {/* 播放浮层（2026-11-04）：**portal 挂到 body**。
        复用 ui/Modal 时视频在 WKWebView 里只有控件不出画面——Modal 渲染在页面组件树内，
        祖先的层叠/布局会干扰 video 合成；挂 body 顶层后与卡片内联播放同一条件。 */}
      {playingTask &&
        createPortal(
          <div
            className="media-player-overlay"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setPlayingTask(null);
            }}
          >
            <div className="media-player-dialog" role="dialog" aria-modal="true">
              <div className="media-player-head">
                <span className="media-player-title" title={playingTask.file_path ?? ""}>
                  {playingTask.file_path?.split("/").pop() ?? t("tool.videoTaskPlay", "播放")}
                </span>
                <Button
                  variant="icon"
                  size="small"
                  aria-label={t("common.close", "关闭")}
                  onClick={() => setPlayingTask(null)}
                >
                  <X size={16} />
                </Button>
              </div>
              <div className="media-player-body">
                <VideoPlayer
                  src={mediaStreamUrl(playingTask.file_path as string)}
                  onError={(message) => console.error("[media] 视频加载失败", message)}
                />
              </div>
              {isTauri() && (
                <div className="media-player-foot">
                  <Button
                    variant="secondary"
                    onClick={() => void openFileLocation(playingTask.file_path as string)}
                  >
                    <FolderOpen size={14} />
                    {t("tool.openDirectory", "打开所在目录")}
                  </Button>
                  <Button variant="secondary" onClick={() => onAct(() => saveTaskAs(playingTask))}>
                    <Save size={14} />
                    {t("tool.videoSaveAs", "另存为")}
                  </Button>
                </div>
              )}
            </div>
          </div>,
          document.body,
        )}

      {/* 失败原因弹窗（2026-11-04）：完整错误在弹窗里读，卡片只留两行摘要 */}
      <Modal
        open={Boolean(reasonTask)}
        title={t("tool.videoReasonTitle", "失败原因")}
        width={560}
        onClose={() => setReasonTask(null)}
        footer={
          reasonTask ? (
            <div className="media-reason-actions">
              <Button variant="secondary" onClick={() => setReasonTask(null)}>
                {t("common.close", "关闭")}
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  const target = reasonTask;
                  setReasonTask(null);
                  void onAct(async () => {
                    const response = await fetch(`/api/media/tasks/${target.id}/retry`, {
                      method: "POST",
                    });
                    if (!response.ok) {
                      const data = await response.json().catch(() => null);
                      throw new Error(data?.detail ?? "重试失败");
                    }
                    toast.success(t("tool.videoRetryStarted", "已重新提交"));
                  });
                }}
              >
                <RotateCcw size={14} />
                {t("tool.videoRetry", "重试")}
              </Button>
            </div>
          ) : null
        }
      >
        <div className="media-reason">
          <div className="media-reason-head">
            <AlertCircle size={15} />
            <span>{reasonTask?.prompt}</span>
          </div>
          <pre className="media-reason-body">{reasonTask?.error ?? ""}</pre>
        </div>
      </Modal>

      {deleteTask && (
        <ConfirmDialog
          title={t("tool.videoDelete", "删除")}
          description={t(
            "tool.videoDeleteConfirm",
            "删除后任务记录与本地文件都会移除，且不可恢复。确定删除这个任务吗？",
          )}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteTask(null)}
        />
      )}
    </div>
  );
}
