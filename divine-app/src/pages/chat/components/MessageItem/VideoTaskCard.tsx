// 视频生成任务卡（035 §9.5）：工具卡不再等结果——提交后从全局 store 按
// task_id 取状态，完成后就地变成播放器；历史回放同样按 task_id 找文件。
import { useEffect, useState } from "react";
import { FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { VideoPlayer } from "@/components/VideoPlayer";
import {
  getTask,
  mediaStreamUrl,
  subscribeMediaTasks,
  type MediaTask,
} from "@/services/mediaTasks";
import { isTauri, openFileLocation } from "@/services/tauri";

export function VideoTaskCard({ taskId }: { taskId: string }) {
  const { t } = useTranslation();
  const [ready, setReady] = useState(false);
  const [task, setTask] = useState<MediaTask | undefined>(() => getTask(taskId));

  useEffect(
    () =>
      subscribeMediaTasks((tasks) => {
        setReady(true);
        setTask(tasks.find((item) => item.id === taskId));
      }),
    [taskId],
  );

  if (!task) {
    // store 还没拉到 / 任务不在列表里：不渲染，避免空卡片
    return ready ? null : null;
  }

  if (task.status === "succeeded" && task.file_path) {
    const fileName = task.file_path.split("/").pop() ?? task.file_path;
    return (
      <div className="video-task-result">
        <VideoPlayer src={mediaStreamUrl(task.file_path)} />
        <div className="video-task-meta">
          <span className="video-task-name" title={task.file_path}>
            {fileName}
          </span>
          {isTauri() && (
            <Button
              variant="icon"
              size="small"
              title={t("tool.openDirectory", "打开所在目录")}
              aria-label={t("tool.openDirectory", "打开所在目录")}
              onClick={() => void openFileLocation(task.file_path as string)}
            >
              <FolderOpen size={13} />
            </Button>
          )}
        </div>
      </div>
    );
  }

  if (task.status === "failed" || task.status === "expired") {
    return (
      <div className="message-error video-task-error">
        <span>
          {task.error ?? t("tool.videoTaskFailed", "视频生成失败，请在「生成任务」面板重试")}
        </span>
      </div>
    );
  }

  // queued / running
  return (
    <div className="video-task-progress">
      <span className="video-task-orb" />
      <span>
        {task.status === "queued"
          ? t("tool.videoTaskQueued", "已排队（前面还有生成中的任务）")
          : t("tool.videoTaskRunning", "视频生成中，可在「生成任务」面板查看进度")}
      </span>
    </div>
  );
}
