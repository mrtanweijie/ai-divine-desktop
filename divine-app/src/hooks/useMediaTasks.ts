// 生成任务的 React 绑定（035 §9.3）：面板/卡片/徽标共用同一份 store。
import { useEffect, useState } from "react";
import { refreshMediaTasks, subscribeMediaTasks, type MediaTask } from "@/services/mediaTasks";

export function useMediaTasks(): {
  tasks: MediaTask[];
  ready: boolean;
  runningCount: number;
} {
  const [tasks, setTasks] = useState<MediaTask[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(
    () =>
      subscribeMediaTasks((next) => {
        setTasks(next);
        setReady(true);
      }),
    [],
  );

  // 冷启动先拉一次（即使没有订阅变化也把徽标填上）
  useEffect(() => {
    void refreshMediaTasks();
  }, []);

  const runningCount = tasks.filter(
    (task) => task.status === "queued" || task.status === "running",
  ).length;
  return { tasks, ready, runningCount };
}
