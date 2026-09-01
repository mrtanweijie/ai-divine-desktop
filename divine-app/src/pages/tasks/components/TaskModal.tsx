import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { DateTimePicker } from "@/components/ui/DateTimePicker";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { toast } from "@/components/ui/Toast";
import {
  createScheduledTask,
  updateScheduledTask,
} from "@/services/scheduledTasks";
import type { ScheduledTask } from "@/types";
import { weekdayLabels, toLocalInputValue } from "../scheduleUtils";
import "./TaskModal.less";

interface TaskModalProps {
  task?: ScheduledTask;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

export function TaskModal({ task, onClose, onSaved }: TaskModalProps) {
  const { t } = useTranslation();
  const [title, setTitle] = useState(task?.title ?? "");
  const [description, setDescription] = useState(task?.description ?? "");
  const [frequency, setFrequency] = useState<ScheduledTask["frequency"]>(
    task?.frequency ?? "once"
  );
  const [runAt, setRunAt] = useState(toLocalInputValue(task?.run_at));
  const [intervalMinutes, setIntervalMinutes] = useState<number | null>(
    task?.interval_minutes ?? 60
  );
  const [runHour, setRunHour] = useState<number | null>(task?.run_hour ?? 8);
  const [runMinute, setRunMinute] = useState<number | null>(
    task?.run_minute ?? 0
  );
  const [daysOfWeek, setDaysOfWeek] = useState<number[]>(
    task?.days_of_week ?? []
  );
  const [dayOfMonth, setDayOfMonth] = useState<number | null>(
    task?.day_of_month ?? 1
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleDay = (day: number) => {
    setDaysOfWeek((prev) =>
      prev.includes(day) ? prev.filter((item) => item !== day) : [...prev, day]
    );
  };

  const handleSave = async () => {
    if (!title.trim()) {
      setError(t("tasks.titleRequired", "请填写任务标题"));
      return;
    }
    if (frequency === "once" && !runAt) {
      setError(t("tasks.onceTimeRequired", "请选择一次性任务的时间"));
      return;
    }
    if (
      frequency === "interval" &&
      (intervalMinutes === null || intervalMinutes < 1)
    ) {
      setError(t("tasks.intervalRequired", "请填写有效的间隔分钟数"));
      return;
    }
    if (frequency === "weekly" && daysOfWeek.length === 0) {
      setError(t("tasks.weekdayRequired", "请至少选择一天"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload: Partial<ScheduledTask> & { title: string } = {
        title: title.trim(),
        description: description.trim(),
        frequency,
      };
      if (frequency === "once") {
        payload.run_at = new Date(runAt).toISOString();
      } else if (frequency === "interval") {
        payload.interval_minutes = intervalMinutes;
      } else if (frequency === "weekly") {
        payload.days_of_week = daysOfWeek;
      } else if (frequency === "monthly") {
        payload.day_of_month = dayOfMonth ?? 1;
      }
      if (frequency !== "once") {
        payload.run_hour = runHour ?? 8;
        payload.run_minute = runMinute ?? 0;
      }
      if (task) {
        await updateScheduledTask(task.id, payload);
      } else {
        await createScheduledTask(payload);
      }
      await onSaved();
      toast.success(
        task
          ? t("tasks.taskUpdated", "定时任务已更新")
          : t("tasks.taskCreated", "定时任务已创建")
      );
    } catch (error) {
      setError(
        error instanceof Error ? error.message : t("tasks.saveFailed", "保存失败")
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      title={
        task
          ? t("tasks.editTitle", "编辑定时任务")
          : t("tasks.createTitle", "新建定时任务")
      }
      onClose={onClose}
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel", "取消")}
          </Button>
          <Button
            variant="primary"
            loading={saving}
            onClick={() => void handleSave()}
          >
            {t("common.save", "保存")}
          </Button>
        </>
      }
    >
      <div className="scheduled-form">
        <Input
          label={t("tasks.titleLabel", "标题")}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder={t("tasks.titlePlaceholder", "例如：买机票")}
        />
        <Input
          label={t("tasks.descriptionLabel", "描述")}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder={t("tasks.descriptionPlaceholder", "提醒内容或任务描述")}
        />
        <Select
          label={t("tasks.frequencyLabel", "频率")}
          value={frequency}
          onChange={(value) =>
            setFrequency(value as ScheduledTask["frequency"])
          }
          options={[
            { value: "once", label: t("tasks.frequencyOnce", "一次性") },
            { value: "interval", label: t("tasks.frequencyInterval", "每隔 x 分钟") },
            { value: "daily", label: t("tasks.frequencyDaily", "每天") },
            { value: "weekly", label: t("tasks.frequencyWeekly", "每周") },
            { value: "monthly", label: t("tasks.frequencyMonthly", "每月") },
          ]}
        />
        {frequency === "once" && (
          <DateTimePicker
            label={t("time.label", "时间")}
            value={runAt}
            onChange={setRunAt}
          />
        )}
        {frequency === "interval" && (
          <Input
            label={t("tasks.intervalLabel", "间隔（分钟）")}
            type="text"
            inputMode="numeric"
            value={intervalMinutes ?? ""}
            onChange={(event) => {
              const digits = event.target.value.replace(/\D/g, "");
              setIntervalMinutes(digits === "" ? null : Number(digits));
            }}
          />
        )}
        {frequency !== "once" && frequency !== "interval" && (
          <>
            <Input
              label={t("tasks.hourLabel", "小时（每天的几点）")}
              type="text"
              inputMode="numeric"
              value={runHour ?? ""}
              onChange={(event) => {
                const digits = event.target.value.replace(/\D/g, "");
                setRunHour(digits === "" ? null : Math.min(23, Number(digits)));
              }}
            />
            <Input
              label={t("tasks.minuteLabel", "分钟（几点几分）")}
              type="text"
              inputMode="numeric"
              value={runMinute ?? ""}
              onChange={(event) => {
                const digits = event.target.value.replace(/\D/g, "");
                setRunMinute(
                  digits === "" ? null : Math.min(59, Number(digits))
                );
              }}
            />
          </>
        )}
        {frequency === "weekly" && (
          <div className="ui-field">
            <span className="ui-field-label">
              {t("tasks.frequencyWeekly", "每周")}
            </span>
            <Flex gap={6} wrap className="weekday-picker">
              {weekdayLabels().map((label, day) => (
                <div
                  key={label}
                  role="checkbox"
                  aria-checked={daysOfWeek.includes(day)}
                  tabIndex={0}
                  className={daysOfWeek.includes(day) ? "active" : ""}
                  onClick={() => toggleDay(day)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      toggleDay(day);
                    }
                  }}
                >
                  {label}
                </div>
              ))}
            </Flex>
          </div>
        )}
        {frequency === "monthly" && (
          <Input
            label={t("tasks.monthlyDate", "每月日期")}
            type="text"
            inputMode="numeric"
            value={dayOfMonth ?? ""}
            onChange={(event) => {
              const digits = event.target.value.replace(/\D/g, "");
              setDayOfMonth(
                digits === "" ? null : Math.min(31, Number(digits))
              );
            }}
          />
        )}
        {error && <div className="scheduled-form-error">{error}</div>}
      </div>
    </Modal>
  );
}
