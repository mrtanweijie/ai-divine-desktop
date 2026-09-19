// One scheduled-task row with frequency icon, actions, and active switch.
import { useEffect, useState } from "react";
import {
  Calendar1,
  CalendarClock,
  CalendarDays,
  CalendarHeart,
  CalendarPlus,
  CalendarSync,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { Flex } from "@/components/ui/Flex";
import { Switch } from "@/components/ui/Switch";
import { listTaskRuns } from "@/services/scheduledTasks";
import type { ScheduledTask, ScheduledTaskType, TaskRun } from "@/types";
import { formatDateTime, formatTaskSchedule } from "../scheduleUtils";

function TaskFrequencyIcon({ task }: { task: ScheduledTask }) {
  if (task.frequency === "daily") return <CalendarClock size={15} />;
  if (task.frequency === "weekly") return <CalendarDays size={15} />;
  if (task.frequency === "monthly") return <CalendarHeart size={15} />;
  if (task.frequency === "once") return <Calendar1 size={15} />;
  return <CalendarSync size={15} />;
}

/** 会写 task_runs 的类型；reminder/agent/monitor 刻意不写（保持改前行为）。 */
const RUN_TYPES: ScheduledTaskType[] = ["webhook", "digest", "interactive"];

const TYPE_LABEL_KEYS: Record<ScheduledTaskType, [string, string]> = {
  reminder: ["tasks.typeReminder", "提醒"],
  agent: ["tasks.typeAgent", "Agent"],
  monitor: ["tasks.typeMonitor", "巡查"],
  webhook: ["tasks.typeWebhook", "推送"],
  digest: ["tasks.typeDigest", "摘要"],
  interactive: ["tasks.typeInteractive", "询问"],
};

const RUN_STATUS_LABELS: Record<string, [string, string]> = {
  pending: ["tasks.runPending", "等待中"],
  running: ["tasks.runRunning", "进行中"],
  succeeded: ["tasks.runSucceeded", "成功"],
  failed: ["tasks.runFailed", "失败"],
  skipped: ["tasks.runSkipped", "跳过"],
};

interface TaskRowProps {
  task: ScheduledTask;
  writingCalendarTaskId: string | null;
  onWriteCalendar: (task: ScheduledTask) => void;
  onEdit: (task: ScheduledTask) => void;
  onDelete: (task: ScheduledTask) => void;
  onToggle: (task: ScheduledTask) => void;
  /** 交互任务的用户决策回包（design 027 §3.4） */
  onDecide?: (task: ScheduledTask, decision: "approve" | "reject") => void;
}

export function TaskRow({
  task,
  writingCalendarTaskId,
  onWriteCalendar,
  onEdit,
  onDelete,
  onToggle,
  onDecide,
}: TaskRowProps) {
  const pending = task.pending_user_action;
  const interactive = task.interactive ?? task.interactive_json;
  const showDecision = Boolean(pending && onDecide);
  const { t } = useTranslation();
  const tracksRuns = RUN_TYPES.includes(task.task_type);
  const [runs, setRuns] = useState<TaskRun[]>([]);

  // 只有会写执行历史的类型才拉取，避免给 reminder/agent/monitor 加无谓请求。
  // 不在 effect 里 setState 重置——渲染侧用 tracksRuns 兜住即可（见下方 lastRun）。
  useEffect(() => {
    if (!tracksRuns) return;
    let alive = true;
    void listTaskRuns(task.id, 1)
      .then((res) => {
        if (alive) setRuns(res.runs ?? []);
      })
      .catch(() => {
        // 拉不到就算了，不影响任务行本身
      });
    return () => {
      alive = false;
    };
  }, [task.id, task.last_run_at, tracksRuns]);

  // 类型切换后旧 runs 可能残留；渲染侧再兜一次，比在 effect 里 setState 干净
  const lastRun = tracksRuns ? runs[0] : undefined;
  const [typeKey, typeFallback] = TYPE_LABEL_KEYS[task.task_type] ?? ["tasks.typeReminder", "提醒"];
  const [runKey, runFallback] = lastRun
    ? (RUN_STATUS_LABELS[lastRun.status] ?? ["tasks.runPending", "等待中"])
    : ["tasks.noRunYet", "尚未执行"];

  return (
    <div key={task.id} className={`task-row ${task.status}`}>
      <div className={`task-row-icon ${task.frequency}`}>
        <TaskFrequencyIcon task={task} />
      </div>
      <div className="task-row-main">
        <div className="task-row-title">
          {task.title}
          <span className={`task-type-badge ${task.task_type}`}>{t(typeKey, typeFallback)}</span>
          {task.status === "paused" && (
            <span className="task-status-badge">{t("tasks.paused", "已暂停")}</span>
          )}
        </div>
        <div className="task-row-schedule">
          {formatTaskSchedule(task)}
          {task.next_run_at && (
            <>
              <span className="task-row-sep">·</span>
              {t("tasks.nextRun", "下次 {{time}}", {
                time: formatDateTime(task.next_run_at),
              })}
            </>
          )}
        </div>
        {task.description && <div className="task-row-desc">{task.description}</div>}
        {tracksRuns && lastRun && (
          <div className="task-row-run">
            <span className={`run-status ${lastRun.status}`}>{t(runKey, runFallback)}</span>
            <span className="task-row-sep">·</span>
            <span>{formatDateTime(lastRun.started_at)}</span>
            {Object.entries(lastRun.delivery_status ?? {}).map(([channel, result]) => (
              <span
                key={channel}
                className={`delivery-chip ${result.ok ? "ok" : "fail"}`}
                title={result.error ?? undefined}
              >
                {channel} {result.ok ? "✓" : "✗"}
              </span>
            ))}
          </div>
        )}
        {tracksRuns && !lastRun && (
          <div className="task-row-run">
            <span className="run-status muted">{t(runKey, runFallback)}</span>
          </div>
        )}
        {showDecision && (
          <div className="task-row-decision">
            <span className="task-row-decision-text">
              {interactive?.notification_body ||
                t("tasks.decisionPrompt", "要现在执行这个任务吗？")}
            </span>
            <Button variant="primary" size="small" onClick={() => onDecide?.(task, "approve")}>
              {interactive?.action_label || t("tasks.decisionApprove", "开始")}
            </Button>
            <Button variant="ghost" size="small" onClick={() => onDecide?.(task, "reject")}>
              {interactive?.reject_label || t("tasks.decisionReject", "跳过")}
            </Button>
          </div>
        )}
      </div>
      <Flex align="center" gap={4} className="task-row-actions">
        <Dropdown
          align="end"
          openOn="hover"
          trigger={
            <Button
              variant="icon"
              size="small"
              title={t("tasks.moreActions", "更多操作")}
              aria-label={t("tasks.moreActions", "更多操作")}
            >
              <MoreHorizontal size={15} />
            </Button>
          }
          items={[
            {
              key: "calendar",
              label: t("tasks.writeCalendar", "写入日程"),
              icon: <CalendarPlus size={13} />,
              disabled: !task.next_run_at || writingCalendarTaskId === task.id,
              onClick: () => onWriteCalendar(task),
            },
            {
              key: "edit",
              label: t("tasks.edit", "编辑"),
              icon: <Pencil size={13} />,
              onClick: () => onEdit(task),
            },
            {
              key: "delete",
              label: t("tasks.delete", "删除"),
              icon: <Trash2 size={13} />,
              onClick: () => onDelete(task),
            },
          ]}
        />
        <Switch checked={task.status === "active"} onChange={() => onToggle(task)} />
      </Flex>
    </div>
  );
}
