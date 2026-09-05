// One scheduled-task row with frequency icon, actions, and active switch.
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
import type { ScheduledTask } from "@/types";
import { formatDateTime, formatTaskSchedule } from "../scheduleUtils";

function TaskFrequencyIcon({ task }: { task: ScheduledTask }) {
  if (task.frequency === "daily") return <CalendarClock size={15} />;
  if (task.frequency === "weekly") return <CalendarDays size={15} />;
  if (task.frequency === "monthly") return <CalendarHeart size={15} />;
  if (task.frequency === "once") return <Calendar1 size={15} />;
  return <CalendarSync size={15} />;
}

interface TaskRowProps {
  task: ScheduledTask;
  writingCalendarTaskId: string | null;
  onWriteCalendar: (task: ScheduledTask) => void;
  onEdit: (task: ScheduledTask) => void;
  onDelete: (task: ScheduledTask) => void;
  onToggle: (task: ScheduledTask) => void;
}

export function TaskRow({
  task,
  writingCalendarTaskId,
  onWriteCalendar,
  onEdit,
  onDelete,
  onToggle,
}: TaskRowProps) {
  const { t } = useTranslation();
  return (
    <div key={task.id} className={`task-row ${task.status}`}>
      <div className={`task-row-icon ${task.frequency}`}>
        <TaskFrequencyIcon task={task} />
      </div>
      <div className="task-row-main">
        <div className="task-row-title">
          {task.title}
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
