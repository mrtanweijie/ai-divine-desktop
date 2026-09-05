import { AlertCircle, BellRing, CalendarX, PanelLeftOpen, Plus, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
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
import { SuggestionCards, type TaskSuggestion } from "./components/SuggestionCards";
import { TaskRow } from "./components/TaskRow";
import "./index.less";

export function ScheduledTasksPage({ onOpenSidebar }: { onOpenSidebar: () => void }) {
  const { t } = useTranslation();
  const suggestions = useMemo<TaskSuggestion[]>(
    () => [
      {
        key: "daily",
        title: t("tasks.suggestionDailyTitle", "每日简报"),
        schedule: t("tasks.suggestionDailySchedule", "工作日 8:00"),
        description: t(
          "tasks.suggestionDailyDescription",
          "以日历、未读电子邮件和优先事项摘要开启每个工作日",
        ),
        frequency: "daily",
        run_hour: 8,
        run_minute: 0,
        days_of_week: [1, 2, 3, 4, 5],
      },
      {
        key: "weekly",
        title: t("tasks.suggestionWeeklyTitle", "每周回顾"),
        schedule: t("tasks.suggestionWeeklySchedule", "星期五 16:00"),
        description: t(
          "tasks.suggestionWeeklyDescription",
          "每周五将你最近的工作整理成简明的状态更新",
        ),
        frequency: "weekly",
        run_hour: 16,
        run_minute: 0,
        days_of_week: [5],
      },
      {
        key: "monitor",
        title: t("tasks.suggestionMonitorTitle", "跟进监控"),
        schedule: t("tasks.suggestionMonitorSchedule", "工作日 9:00"),
        description: t(
          "tasks.suggestionMonitorDescription",
          "查看最近的电子邮箱和日历活动，并标记需要你关注的事项",
        ),
        frequency: "daily",
        run_hour: 9,
        run_minute: 0,
        days_of_week: [1, 2, 3, 4, 5],
      },
    ],
    [t],
  );
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [notificationGranted, setNotificationGranted] = useState<boolean | null>(null);
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [creatingSuggestion, setCreatingSuggestion] = useState<string | null>(null);
  const [createdSuggestion, setCreatedSuggestion] = useState<string | null>(null);
  const [taskModal, setTaskModal] = useState<
    { mode: "create" } | { mode: "edit"; task: ScheduledTask } | null
  >(null);
  const [deleteTask, setDeleteTask] = useState<ScheduledTask | null>(null);
  const [writingCalendarTaskId, setWritingCalendarTaskId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [taskData, eventData] = await Promise.all([listScheduledTasks(), listCalendarEvents()]);
      setTasks(taskData.tasks);
      setEvents(eventData.events);
      await syncTaskNotifications(taskData.tasks);
      await syncCalendarToSystem(eventData.events, (message) => setCalendarError(message));
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
        task.description.toLowerCase().includes(keyword),
    );
  }, [search, tasks]);

  const handleCreateSuggestion = useCallback(
    async (suggestion: TaskSuggestion) => {
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
        toast.success(
          t("tasks.created", "已创建任务：{{title}}", {
            title: suggestion.title,
          }),
        );
        setTimeout(() => setCreatedSuggestion(null), 1800);
        const granted = await ensureNotificationPermission();
        setNotificationGranted(granted);
        await syncTaskNotifications([...tasks, task]).catch(() => undefined);
      } catch (error) {
        setActionError(
          error instanceof Error ? error.message : t("tasks.createFailed", "创建定时任务失败"),
        );
      } finally {
        setCreatingSuggestion(null);
      }
    },
    [t, tasks],
  );

  const handleToggleTask = useCallback(
    async (task: ScheduledTask) => {
      setActionError(null);
      try {
        const nextStatus = task.status === "active" ? "paused" : "active";
        const updated = await updateScheduledTask(task.id, {
          status: nextStatus,
        });
        setTasks((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
        toast.success(
          nextStatus === "paused"
            ? t("tasks.paused", "任务已暂停")
            : t("tasks.resumed", "任务已恢复"),
        );
        await syncTaskNotifications(tasks.map((item) => (item.id === updated.id ? updated : item)));
      } catch (error) {
        setActionError(
          error instanceof Error ? error.message : t("tasks.actionFailed", "操作失败，请重试"),
        );
      }
    },
    [t, tasks],
  );

  const handleDeleteTask = useCallback(
    async (task: ScheduledTask) => {
      setActionError(null);
      try {
        await deleteScheduledTask(task.id);
        const next = tasks.filter((item) => item.id !== task.id);
        setTasks(next);
        setDeleteTask(null);
        toast.success(t("tasks.deleted", "任务已删除"));
        await syncTaskNotifications(next);
      } catch (error) {
        setActionError(
          error instanceof Error ? error.message : t("tasks.deleteFailed", "删除失败，请重试"),
        );
      }
    },
    [t, tasks],
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
            end_at: new Date(new Date(task.next_run_at).getTime() + 60 * 60 * 1000).toISOString(),
            notes: task.description,
            task_id: task.id,
          });
          next = [...events, event];
          setEvents(next);
        }
        await syncCalendarToSystem(next, (message) => setCalendarError(message));
        toast.success(
          existing
            ? t("tasks.calendarSynced", "日程已同步到系统日历")
            : t("tasks.calendarWritten", "已写入日程"),
        );
      } catch (error) {
        setActionError(
          error instanceof Error ? error.message : t("tasks.calendarWriteFailed", "写入日程失败"),
        );
      } finally {
        setWritingCalendarTaskId(null);
      }
    },
    [events, t, writingCalendarTaskId],
  );

  const handleEnableNotifications = useCallback(async () => {
    setActionError(null);
    try {
      const granted = await ensureNotificationPermission();
      setNotificationGranted(granted);
    } catch (error) {
      setActionError(
        error instanceof Error
          ? error.message
          : t("tasks.enableNotificationFailed", "开启通知失败"),
      );
    }
  }, [t]);

  return (
    <div className="scheduled-page">
      <header className="scheduled-header">
        <Flex align="center" gap={8} className="scheduled-header-actions">
          <Button
            variant="icon"
            className="scheduled-sidebar-button"
            onClick={onOpenSidebar}
            aria-label={t("common.expandSessionList", "展开会话列表")}
            title={t("session.list", "会话列表")}
          >
            <PanelLeftOpen size={15} />
          </Button>
          <div className="scheduled-search">
            <Search size={14} />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("tasks.search", "搜索已安排任务")}
              aria-label={t("tasks.search", "搜索已安排任务")}
            />
          </div>
          <Button variant="primary" size="small" onClick={() => setTaskModal({ mode: "create" })}>
            <Plus size={14} />
            {t("tasks.new", "新建任务")}
          </Button>
        </Flex>
      </header>

      {notificationGranted === false && (
        <div className="scheduled-notice">
          <BellRing size={15} />
          <span>{t("tasks.notificationDisabled", "系统通知未开启，到点可能收不到提醒。")}</span>
          <Button size="small" onClick={() => void handleEnableNotifications()}>
            {t("tasks.enableNotifications", "开启通知")}
          </Button>
        </div>
      )}
      {actionError && (
        <div className="scheduled-notice calendar-notice">
          <AlertCircle size={15} />
          <span>{actionError}</span>
          <Button size="small" variant="ghost" onClick={() => setActionError(null)}>
            {t("common.close", "关闭")}
          </Button>
        </div>
      )}
      {calendarError && (
        <div className="scheduled-notice calendar-notice">
          <CalendarX size={15} />
          <span>
            {t("tasks.calendarSyncFailed", "系统日历同步失败：{{message}}", {
              message: calendarError,
            })}
          </span>
          <Button size="small" variant="ghost" onClick={() => setCalendarError(null)}>
            {t("common.close", "关闭")}
          </Button>
        </div>
      )}

      {loading ? (
        <div className="scheduled-empty">{t("common.loading", "加载中...")}</div>
      ) : (
        <div className="scheduled-content">
          {filteredTasks.length > 0 ? (
            <div className="task-list">
              {filteredTasks.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  writingCalendarTaskId={writingCalendarTaskId}
                  onWriteCalendar={(item) => void handleWriteCalendar(item)}
                  onEdit={(item) => setTaskModal({ mode: "edit", task: item })}
                  onDelete={setDeleteTask}
                  onToggle={(item) => void handleToggleTask(item)}
                />
              ))}
            </div>
          ) : (
            <div className="scheduled-empty">
              {search
                ? t("tasks.noMatches", "没有匹配的任务")
                : t("tasks.noneYet", "还没有定时任务")}
            </div>
          )}

          {!search && (
            <SuggestionCards
              suggestions={suggestions}
              creatingSuggestion={creatingSuggestion}
              createdSuggestion={createdSuggestion}
              onCreate={(suggestion) => void handleCreateSuggestion(suggestion)}
            />
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
          title={t("tasks.deleteTitle", "删除定时任务")}
          description={t(
            "tasks.deleteConfirm",
            "删除后任务“{{title}}”将不再提醒，关联的日程也会一并删除。",
            { title: deleteTask.title },
          )}
          onConfirm={() => void handleDeleteTask(deleteTask)}
          onCancel={() => setDeleteTask(null)}
        />
      )}
    </div>
  );
}
