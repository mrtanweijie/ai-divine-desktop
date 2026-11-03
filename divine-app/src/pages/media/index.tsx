// 生成任务面板（035 §9）：进行中 / 已完成两组，操作按状态给。
// 「不再等待」= 本地隐藏（轮询继续，云端跑完仍可取回）——说"已取消"是撒谎。
import { useCallback, useMemo, useState } from "react";
import { Clapperboard, FolderOpen, PanelLeftOpen, Play, RotateCcw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { toast } from "@/components/ui/Toast";
import { VideoPlayer } from "@/components/VideoPlayer";
import { useMediaTasks } from "@/hooks/useMediaTasks";
import { dismissMediaTask, mediaStreamUrl, type MediaTask } from "@/services/mediaTasks";
import { isTauri, openFileLocation } from "@/services/tauri";
import "./index.less";

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

function formatSince(task: MediaTask): string {
  const started = new Date(task.created_at).getTime();
  if (Number.isNaN(started)) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function paramChips(task: MediaTask): string {
  const params = task.params || {};
  const chips: string[] = [];
  if (params.duration) chips.push(`${params.duration}s`);
  if (params.resolution) chips.push(String(params.resolution));
  if (params.aspect_ratio) chips.push(String(params.aspect_ratio));
  if (params.mode === "first_frame") chips.push("图生视频");
  if (params.mode === "first_last") chips.push("首尾帧");
  if (params.source === "article") chips.push("资讯");
  return chips.join(" · ");
}

export function MediaTasksPage({ onOpenSidebar }: { onOpenSidebar: () => void }) {
  const { t } = useTranslation();
  const { tasks } = useMediaTasks();
  const [showDismissed, setShowDismissed] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const running = useMemo(
    () =>
      tasks.filter(
        (task) =>
          (task.status === "queued" || task.status === "running") && !(task.extras || {}).dismissed,
      ),
    [tasks],
  );
  const dismissedCount = useMemo(
    () =>
      tasks.filter(
        (task) =>
          (task.status === "queued" || task.status === "running") && (task.extras || {}).dismissed,
      ).length,
    [tasks],
  );
  const done = useMemo(
    () =>
      tasks.filter(
        (task) =>
          task.status !== "queued" && task.status !== "running" && !(task.extras || {}).dismissed,
      ),
    [tasks],
  );

  const act = useCallback(async (action: () => Promise<void>) => {
    try {
      await action();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  }, []);

  const rows = (items: MediaTask[], section: "running" | "done") =>
    items.map((task) => {
      const failed = task.status === "failed" || task.status === "expired";
      const succeeded = task.status === "succeeded" && task.file_path;
      const expanded = expandedId === task.id;
      return (
        <div key={task.id} className="media-task-row">
          <div className="media-task-main">
            <div className="media-task-thumb">
              {succeeded && expanded ? (
                <VideoPlayer src={mediaStreamUrl(task.file_path as string)} />
              ) : succeeded ? (
                <Button
                  variant="icon"
                  className="media-task-play"
                  aria-label={t("tool.videoTaskPlay", "播放")}
                  title={t("tool.videoTaskPlay", "播放")}
                  onClick={() => setExpandedId(task.id)}
                >
                  <Play size={16} />
                </Button>
              ) : failed ? (
                <span className="media-task-state-failed">
                  {t("tool.videoTaskStateFailed", "失败")}
                </span>
              ) : (
                <span className="media-task-orb" />
              )}
            </div>
            <div className="media-task-info">
              <div className="media-task-prompt" title={task.prompt}>
                {task.prompt}
              </div>
              <div className="media-task-status">
                {section === "running"
                  ? `${task.status === "queued" ? t("tool.videoTaskQueued", "已排队") : t("tool.videoTaskRunningShort", "生成中")} · ${formatSince(task)}`
                  : task.status === "succeeded"
                    ? new Date(task.updated_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : (task.error ?? task.status)}
                {section === "running" || paramChips(task) ? ` · ${paramChips(task)}` : ""}
              </div>
            </div>
            <div className="media-task-actions">
              {section === "running" && (
                <Button
                  variant="ghost"
                  size="small"
                  onClick={() =>
                    void act(async () => {
                      await dismissMediaTask(task.id);
                      toast.success(
                        t("tool.videoDismissedToast", "已不再等待；云端仍会跑完，稍后可以回来取"),
                      );
                    })
                  }
                >
                  {t("tool.videoDismiss", "不再等待")}
                </Button>
              )}
              {succeeded && (
                <>
                  <Button
                    variant="ghost"
                    size="small"
                    onClick={() => setExpandedId(expanded ? null : task.id)}
                  >
                    {expanded ? t("tool.videoCollapse", "收起") : t("tool.videoTaskPlay", "播放")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="small"
                    onClick={() => void act(() => saveTaskAs(task))}
                  >
                    {t("tool.videoSaveAs", "另存为")}
                  </Button>
                  {isTauri() && (
                    <Button
                      variant="ghost"
                      size="small"
                      onClick={() => void openFileLocation(task.file_path as string)}
                      title={t("tool.openDirectory", "打开所在目录")}
                      aria-label={t("tool.openDirectory", "打开所在目录")}
                    >
                      <FolderOpen size={13} />
                    </Button>
                  )}
                </>
              )}
              {failed && (
                <Button
                  variant="ghost"
                  size="small"
                  onClick={() =>
                    void act(async () => {
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
                  <RotateCcw size={12} />
                  {t("tool.videoRetry", "重试")}
                </Button>
              )}
              {section === "done" && (
                <Button
                  variant="ghost"
                  size="small"
                  aria-label={t("tool.videoDelete", "删除")}
                  title={t("tool.videoDelete", "删除")}
                  onClick={() =>
                    void act(async () => {
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
                  <Trash2 size={12} />
                </Button>
              )}
            </div>
          </div>
        </div>
      );
    });

  return (
    <div className="media-tasks-page">
      <header className="media-tasks-header">
        <div className="media-tasks-title">
          <Clapperboard size={16} />
          <h1>{t("tool.mediaPageTitle", "生成任务")}</h1>
        </div>
        <Flex align="center" gap={8}>
          <Input
            value=""
            readOnly
            placeholder={t("tool.mediaPageHint", "在对话里说「生成一段…的视频」即可发起")}
            className="media-tasks-hint"
          />
          <Button
            variant="icon"
            className="sidebar-open-button"
            aria-label={t("session.openSidebar", "打开侧栏")}
            onClick={onOpenSidebar}
          >
            <PanelLeftOpen size={14} />
          </Button>
        </Flex>
      </header>

      <div className="media-tasks-body">
        <h2 className="media-section-title">
          {t("tool.mediaSectionRunning", "进行中")}
          {running.length > 0 ? ` · ${running.length}` : ""}
        </h2>
        {running.length === 0 ? (
          <p className="media-empty">{t("tool.mediaEmptyRunning", "没有正在生成的任务")}</p>
        ) : (
          rows(running, "running")
        )}
        {dismissedCount > 0 && (
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
                  count: dismissedCount,
                })}
          </div>
        )}
        {showDismissed &&
          rows(
            tasks.filter(
              (task) =>
                (task.status === "queued" || task.status === "running") &&
                (task.extras || {}).dismissed,
            ),
            "running",
          )}

        <h2 className="media-section-title">{t("tool.mediaSectionDone", "已完成（今天）")}</h2>
        {done.length === 0 ? (
          <p className="media-empty">{t("tool.mediaEmptyDone", "还没有完成的任务")}</p>
        ) : (
          rows(done, "done")
        )}
      </div>
    </div>
  );
}
