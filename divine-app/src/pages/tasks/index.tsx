import {
  AlertCircle,
  BellRing,
  Calendar1,
  CalendarClock,
  CalendarHeart,
  CalendarPlus,
  CalendarSync,
  CalendarX,
  Check,
  ChevronRight,
  Clock,
  MoreHorizontal,
  PanelLeftOpen,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Dropdown } from "@/components/ui/Dropdown";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { toast } from "@/components/ui/Toast";
import {
  createCalendarEvent,
  createScheduledTask,
  deleteScheduledTask,
  ensureNotificationPermission,
  isNotificationGranted,
  listCalendarEvents,
  listScheduledTasks,
  subscribeEventsChanged,
  subscribeTasksChanged,
  syncCalendarToSystem,
  syncTaskNotifications,
  updateScheduledTask,
} from "@/services/scheduledTasks";
import type { CalendarEvent, ScheduledTask } from "@/types";
import { TaskModal } from "./components/TaskModal";
import { formatDateTime, formatTaskSchedule } from "./scheduleUtils";
import "./index.less";

function TaskFrequencyIcon({ task }: { task: ScheduledTask }) {
  if (task.frequency === "daily") return <Clock size={15} />;
  if (task.frequency === "weekly") return <CalendarClock size={15} />;
  if (task.frequency === "monthly") return <CalendarHeart size={15} />;
  if (task.frequency === "once") return <Calendar1 size={15} />;
  return <CalendarSync size={15} />;
}

const SUGGESTIONS: {
  key: string;
  title: string;
  schedule: string;
  description: string;
  frequency: ScheduledTask["frequency"];
  run_hour: number;
  run_minute: number;
  days_of_week: number[];
}[] = [
  {
    key: "daily",
    title: "每日简报",
    schedule: "工作日 8:00",
    description: "以日历、未读电子邮件和优先事项摘要开启每个工作日",
    frequency: "daily",
    run_hour: 8,
    run_minute: 0,
    days_of_week: [1, 2, 3, 4, 5],
  },
  {
    key: "weekly",
    title: "每周回顾",
    schedule: "星期五 16:00",
    description: "每周五将你最近的工作整理成简明的状态更新",
    frequency: "weekly",
    run_hour: 16,
    run_minute: 0,
    days_of_week: [5],
  },
  {
    key: "monitor",
    title: "跟进监控",
    schedule: "工作日 9:00",
    description: "查看最近的电子邮箱和日历活动，并标记需要你关注的事项",
    frequency: "daily",
    run_hour: 9,
    run_minute: 0,
    days_of_week: [1, 2, 3, 4, 5],
  },
];

export function ScheduledTasksPage({
  onOpenSidebar,
}: {
  onOpenSidebar: () => void;
}) {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [notificationGranted, setNotificationGranted] = useState<boolean | null>(
    null
  );
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [creatingSuggestion, setCreatingSuggestion] = useState<string | null>(
    null
  );
  const [createdSuggestion, setCreatedSuggestion] = useState<string | null>(
    null
  );
  const [taskModal, setTaskModal] = useState<
    { mode: "create" } | { mode: "edit"; task: ScheduledTask } | null
  >(null);
  const [deleteTask, setDeleteTask] = useState<ScheduledTask | null>(null);
  const [writingCalendarTaskId, setWritingCalendarTaskId] = useState<
    string | null
  >(null);

  const refresh = useCallback(async () => {
    try {
      const [taskData, eventData] = await Promise.all([
        listScheduledTasks(),
        listCalendarEvents(),
      ]);
      setTasks(taskData.tasks);
      setEvents(eventData.events);
      await syncTaskNotifications(taskData.tasks);
      await syncCalendarToSystem(eventData.events, (message) =>
        setCalendarError(message)
      );
      setNotificationGranted(await isNotificationGranted());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const unsubscribeTasks = subscribeTasksChanged(() => void refresh());
    const unsubscribeEvents = subscribeEventsChanged(() => void refresh());
    return () => {
      unsubscribeTasks();
      unsubscribeEvents();
    };
  }, [refresh]);

  const filteredTasks = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) return tasks;
    return tasks.filter(
      (task) =>
        task.title.toLowerCase().includes(keyword) ||
        task.description.toLowerCase().includes(keyword)
    );
  }, [search, tasks]);

  const handleCreateSuggestion = useCallback(
    async (suggestion: (typeof SUGGESTIONS)[number]) => {
      setCreatingSuggestion(suggestion.key);
      setActionError(null);
      try {
        const task = await createScheduledTask({
          title: suggestion.title,
          description: suggestion.description,
          frequency: suggestion.frequency,
          run_hour: suggestion.run_hour,
          run_minute: suggestion.run_minute,
          days_of_week: suggestion.days_of_week,
        });
        setTasks((prev) => [...prev, task]);
        setCreatedSuggestion(suggestion.key);
        toast.success(`已创建任务：${suggestion.title}`);
        setTimeout(() => setCreatedSuggestion(null), 1800);
        const granted = await ensureNotificationPermission();
        setNotificationGranted(granted);
        await syncTaskNotifications([...tasks, task]).catch(() => undefined);
      } catch (error) {
        setActionError(
          error instanceof Error ? error.message : "创建定时任务失败"
        );
      } finally {
        setCreatingSuggestion(null);
      }
    },
    [tasks]
  );

  const handleToggleTask = useCallback(
    async (task: ScheduledTask) => {
      setActionError(null);
      try {
        const nextStatus = task.status === "active" ? "paused" : "active";
        const updated = await updateScheduledTask(task.id, {
          status: nextStatus,
        });
        setTasks((prev) =>
          prev.map((item) => (item.id === updated.id ? updated : item))
        );
        toast.success(nextStatus === "paused" ? "任务已暂停" : "任务已恢复");
        await syncTaskNotifications(
          tasks.map((item) => (item.id === updated.id ? updated : item))
        );
      } catch (error) {
        setActionError(
          error instanceof Error ? error.message : "操作失败，请重试"
        );
      }
    },
    [tasks]
  );

  const handleDeleteTask = useCallback(
    async (task: ScheduledTask) => {
      setActionError(null);
      try {
        await deleteScheduledTask(task.id);
        const next = tasks.filter((item) => item.id !== task.id);
        setTasks(next);
        setDeleteTask(null);
        toast.success("任务已删除");
        await syncTaskNotifications(next);
      } catch (error) {
        setActionError(
          error instanceof Error ? error.message : "删除失败，请重试"
        );
      }
    },
    [tasks]
  );

  const handleWriteCalendar = useCallback(
    async (task: ScheduledTask) => {
      if (!task.next_run_at) return;
      if (writingCalendarTaskId === task.id) return;
      setWritingCalendarTaskId(task.id);
      setActionError(null);
      try {
        const existing = events.find((item) => item.task_id === task.id);
        let next: CalendarEvent[];
        if (existing) {
          next = events;
        } else {
          const event = await createCalendarEvent({
            title: task.title,
            start_at: task.next_run_at,
            end_at: new Date(
              new Date(task.next_run_at).getTime() + 60 * 60 * 1000
            ).toISOString(),
            notes: task.description,
            task_id: task.id,
          });
          next = [...events, event];
          setEvents(next);
        }
        await syncCalendarToSystem(next, (message) =>
          setCalendarError(message)
        );
        toast.success(existing ? "日程已同步到系统日历" : "已写入日程");
      } catch (error) {
        setActionError(
          error instanceof Error ? error.message : "写入日程失败"
        );
      } finally {
        setWritingCalendarTaskId(null);
      }
    },
    [events, writingCalendarTaskId]
  );

  const handleEnableNotifications = useCallback(async () => {
    setActionError(null);
    try {
      const granted = await ensureNotificationPermission();
      setNotificationGranted(granted);
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "开启通知失败"
      );
    }
  }, []);

  return (
    <div className="scheduled-page">
      <header className="scheduled-header">
        <Flex align="center" gap={8} className="scheduled-header-actions">
          <Button
            variant="icon"
            className="scheduled-sidebar-button"
            onClick={onOpenSidebar}
            aria-label="展开会话列表"
            title="会话列表"
          >
            <PanelLeftOpen size={15} />
          </Button>
          <div className="scheduled-search">
            <Search size={14} />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索已安排任务"
              aria-label="搜索已安排任务"
            />
          </div>
          <Button
            variant="primary"
            size="small"
            onClick={() => setTaskModal({ mode: "create" })}
          >
            <Plus size={14} />
            新建任务
          </Button>
        </Flex>
      </header>

      {notificationGranted === false && (
        <div className="scheduled-notice">
          <BellRing size={15} />
          <span>系统通知未开启，到点可能收不到提醒。</span>
          <Button size="small" onClick={() => void handleEnableNotifications()}>
            开启通知
          </Button>
        </div>
      )}
      {actionError && (
        <div className="scheduled-notice calendar-notice">
          <AlertCircle size={15} />
          <span>{actionError}</span>
          <Button
            size="small"
            variant="ghost"
            onClick={() => setActionError(null)}
          >
            关闭
          </Button>
        </div>
      )}
      {calendarError && (
        <div className="scheduled-notice calendar-notice">
          <CalendarX size={15} />
          <span>系统日历同步失败：{calendarError}</span>
          <Button
            size="small"
            variant="ghost"
            onClick={() => setCalendarError(null)}
          >
            关闭
          </Button>
        </div>
      )}

      {loading ? (
        <div className="scheduled-empty">加载中...</div>
      ) : (
        <div className="scheduled-content">
          {filteredTasks.length > 0 ? (
            <div className="task-list">
              {filteredTasks.map((task) => (
                <div key={task.id} className={`task-row ${task.status}`}>
                  <div className={`task-row-icon ${task.frequency}`}>
                    <TaskFrequencyIcon task={task} />
                  </div>
                  <div className="task-row-main">
                    <div className="task-row-title">
                      {task.title}
                      {task.status === "paused" && (
                        <span className="task-status-badge">已暂停</span>
                      )}
                    </div>
                    <div className="task-row-schedule">
                      {formatTaskSchedule(task)}
                      {task.next_run_at && (
                        <>
                          <span className="task-row-sep">·</span>
                          下次 {formatDateTime(task.next_run_at)}
                        </>
                      )}
                    </div>
                    {task.description && (
                      <div className="task-row-desc">{task.description}</div>
                    )}
                  </div>
                  <Flex align="center" gap={4} className="task-row-actions">
                    <Dropdown
                      align="end"
                      trigger={
                        <Button
                          variant="icon"
                          size="small"
                          title="更多操作"
                          aria-label="更多操作"
                        >
                          <MoreHorizontal size={15} />
                        </Button>
                      }
                      items={[
                        {
                          key: "calendar",
                          label: "写入日程",
                          icon: <CalendarPlus size={13} />,
                          disabled:
                            !task.next_run_at ||
                            writingCalendarTaskId === task.id,
                          onClick: () => void handleWriteCalendar(task),
                        },
                        {
                          key: "edit",
                          label: "编辑",
                          icon: <Pencil size={13} />,
                          onClick: () => setTaskModal({ mode: "edit", task }),
                        },
                        {
                          key: "delete",
                          label: "删除",
                          icon: <Trash2 size={13} />,
                          onClick: () => setDeleteTask(task),
                        },
                      ]}
                    />
                    <Switch
                      checked={task.status === "active"}
                      onChange={() => void handleToggleTask(task)}
                    />
                  </Flex>
                </div>
              ))}
            </div>
          ) : (
            <div className="scheduled-empty">
              {search ? "没有匹配的任务" : "还没有定时任务"}
            </div>
          )}

          {!search && (
            <section className="suggestion-section">
              <h2>建议</h2>
              <div className="suggestion-grid">
                {SUGGESTIONS.map((suggestion) => (
                  <div
                    key={suggestion.key}
                    className={`suggestion-card${
                      creatingSuggestion === suggestion.key ? " creating" : ""
                    }`}
                    role="button"
                    tabIndex={creatingSuggestion ? -1 : 0}
                    aria-disabled={creatingSuggestion !== null}
                    onClick={() => void handleCreateSuggestion(suggestion)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        void handleCreateSuggestion(suggestion);
                        event.currentTarget.blur();
                      }
                    }}
                  >
                    <div className="suggestion-head">
                      <span className="suggestion-title">
                        {suggestion.title}
                      </span>
                      {creatingSuggestion === suggestion.key ? (
                        <span className="suggestion-state">创建中...</span>
                      ) : createdSuggestion === suggestion.key ? (
                        <span className="suggestion-state created">
                          <Check size={13} />
                          已创建
                        </span>
                      ) : (
                        <ChevronRight size={14} />
                      )}
                    </div>
                    <div className="suggestion-schedule">
                      {suggestion.schedule}
                    </div>
                    <div className="suggestion-desc">
                      {suggestion.description}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {taskModal && (
        <TaskModal
          task={taskModal.mode === "edit" ? taskModal.task : undefined}
          onClose={() => setTaskModal(null)}
          onSaved={async () => {
            setTaskModal(null);
            await refresh();
          }}
        />
      )}
      {deleteTask && (
        <ConfirmDialog
          title="删除定时任务"
          description={`删除后任务“${deleteTask.title}”将不再提醒，关联的日程也会一并删除。`}
          onConfirm={() => void handleDeleteTask(deleteTask)}
          onCancel={() => setDeleteTask(null)}
        />
      )}
    </div>
  );
}
