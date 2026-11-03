// 生成任务页（035 §9，交互对齐技能页）：统计行 + 筛选 chips + 三列任务卡片。
// 卡片：状态图标 + prompt + 参数 chips + 摘要 + 底部主操作；
// 播放在卡片内展开（展开时占满整行）。
import { AlertCircle, Clapperboard, FolderOpen, Play, RotateCcw, Save, Trash2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
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
  playing,
  onTogglePlay,
  onAct,
}: {
  task: MediaTask;
  playing: boolean;
  onTogglePlay: (id: string) => void;
  onAct: (action: () => Promise<void>) => void;
}) {
  const { t } = useTranslation();
  const running = isRunning(task);
  const failed = task.status === "failed" || task.status === "expired";
  const succeeded = task.status === "succeeded" && Boolean(task.file_path);
  const chips = paramChips(task);
  const fileName = task.file_path?.split("/").pop() ?? "";

  const summary = succeeded
    ? `${new Date(task.updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · ${fileName}`
    : running
      ? `${statusLabel(task, t)} · ${formatSince(task)}`
      : (task.error ?? statusLabel(task, t));

  return (
    <div className={`media-task-card${playing ? " is-playing" : ""}${failed ? " is-failed" : ""}`}>
      <div className="media-task-head">
        <div
          className={`media-task-icon${running ? " is-running" : ""}${failed ? " is-failed" : ""}`}
        >
          {running ? (
            <span className="media-task-orb" />
          ) : failed ? (
            <AlertCircle size={15} />
          ) : (
            <Play size={14} />
          )}
        </div>
        <div className="media-task-title-block">
          <div className="media-task-title" title={task.prompt}>
            {task.prompt || t("tool.mediaUnnamedTask", "未命名任务")}
          </div>
          <div className="media-task-badges">
            <span
              className={`media-task-badge${failed ? " is-failed" : ""}${
                task.status === "succeeded" ? " is-done" : ""
              }`}
            >
              {statusLabel(task, t)}
            </span>
            {chips.map((chip) => (
              <span key={chip} className="media-task-badge muted">
                {chip}
              </span>
            ))}
          </div>
        </div>
      </div>

      {playing && succeeded && (
        <div className="media-task-player">
          <VideoPlayer src={mediaStreamUrl(task.file_path as string)} />
        </div>
      )}

      <div className="media-task-desc" title={succeeded ? (task.file_path ?? "") : undefined}>
        {summary}
      </div>

      <div className="media-task-footer">
        <div className="media-task-footer-side">
          {succeeded && isTauri() && (
            <>
              <Button
                variant="icon"
                size="small"
                title={t("tool.openDirectory", "打开所在目录")}
                aria-label={t("tool.openDirectory", "打开所在目录")}
                onClick={() => void openFileLocation(task.file_path as string)}
              >
                <FolderOpen size={13} />
              </Button>
              <Button
                variant="icon"
                size="small"
                title={t("tool.videoSaveAs", "另存为")}
                aria-label={t("tool.videoSaveAs", "另存为")}
                onClick={() => onAct(() => saveTaskAs(task))}
              >
                <Save size={13} />
              </Button>
            </>
          )}
          {failed && (
            <Button
              variant="icon"
              size="small"
              title={t("tool.videoRetry", "重试")}
              aria-label={t("tool.videoRetry", "重试")}
              onClick={() =>
                onAct(async () => {
                  const response = await fetch(`/api/media/tasks/${task.id}/retry`, {
                    method: "POST",
                  });
                  if (!response.ok) {
                    const data = await response.json().catch(() => null);
                    throw new Error(data?.detail ?? "重试失败");
                  }
                  toast.success(t("tool.videoRetryStarted", "已重新提交"));
                })
              }
            >
              <RotateCcw size={13} />
            </Button>
          )}
          {!running && (
            <Button
              variant="icon"
              size="small"
              title={t("tool.videoDelete", "删除")}
              aria-label={t("tool.videoDelete", "删除")}
              onClick={() =>
                onAct(async () => {
                  const response = await fetch(`/api/media/tasks/${task.id}`, {
                    method: "DELETE",
                  });
                  if (!response.ok) {
                    const data = await response.json().catch(() => null);
                    throw new Error(data?.detail ?? "删除失败");
                  }
                })
              }
            >
              <Trash2 size={13} />
            </Button>
          )}
        </div>
        <div
          role="button"
          tabIndex={0}
          className="media-task-footer-action"
          onClick={() => {
            if (running) {
              onAct(async () => {
                await dismissMediaTask(task.id);
                toast.success(
                  t("tool.videoDismissedToast", "已不再等待；云端仍会跑完，稍后可以回来取"),
                );
              });
              return;
            }
            if (succeeded) onTogglePlay(task.id);
          }}
          onKeyDown={(event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            if (running) {
              onAct(async () => {
                await dismissMediaTask(task.id);
              });
              return;
            }
            if (succeeded) onTogglePlay(task.id);
          }}
        >
          {running
            ? t("tool.videoDismiss", "不再等待")
            : succeeded
              ? playing
                ? t("tool.videoCollapse", "收起")
                : t("tool.videoTaskPlay", "播放 ▸")
              : t("tool.videoTaskNoAction", "查看原因")}
        </div>
      </div>
    </div>
  );
}

export function MediaTasksPage() {
  const { t } = useTranslation();
  const { tasks } = useMediaTasks();
  const [filter, setFilter] = useState<MediaFilter>("all");
  const [showDismissed, setShowDismissed] = useState(false);
  const [playingId, setPlayingId] = useState<string | null>(null);

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

  const onAct = useCallback(async (action: () => Promise<void>) => {
    try {
      await action();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  }, []);

  const togglePlay = useCallback((id: string) => {
    setPlayingId((current) => (current === id ? null : id));
  }, []);

  return (
    <div className="media-page">
      <div className="media-toolbar">
        <div className="media-summary">
          <span>{t("tool.mediaSummaryTotal", "共 {{count}} 个任务", { count: tasks.length })}</span>
          <span className="media-summary-sep">·</span>
          <span>
            {t("tool.mediaSummaryRunning", "进行中 {{count}}", { count: running.length })}
          </span>
          <span className="media-summary-sep">·</span>
          <span>{t("tool.mediaSummaryDone", "已完成 {{count}}", { count: done.length })}</span>
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
                playing={playingId === task.id}
                onTogglePlay={togglePlay}
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
    </div>
  );
}
