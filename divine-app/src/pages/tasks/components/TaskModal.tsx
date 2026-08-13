import { useState } from "react";
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
import { WEEKDAYS, toLocalInputValue } from "../scheduleUtils";
import "./TaskModal.less";

interface TaskModalProps {
  task?: ScheduledTask;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

export function TaskModal({ task, onClose, onSaved }: TaskModalProps) {
  const [title, setTitle] = useState(task?.title ?? "");
  const [description, setDescription] = useState(task?.description ?? "");
  const [frequency, setFrequency] = useState<ScheduledTask["frequency"]>(
    task?.frequency ?? "once"
  );
  const [runAt, setRunAt] = useState(toLocalInputValue(task?.run_at));
  const [intervalMinutes, setIntervalMinutes] = useState(
    task?.interval_minutes ?? 60
  );
  const [runHour, setRunHour] = useState(task?.run_hour ?? 8);
  const [runMinute, setRunMinute] = useState(task?.run_minute ?? 0);
  const [daysOfWeek, setDaysOfWeek] = useState<number[]>(
    task?.days_of_week ?? []
  );
  const [dayOfMonth, setDayOfMonth] = useState(task?.day_of_month ?? 1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleDay = (day: number) => {
    setDaysOfWeek((prev) =>
      prev.includes(day) ? prev.filter((item) => item !== day) : [...prev, day]
    );
  };

  const handleSave = async () => {
    if (!title.trim()) {
      setError("请填写任务标题");
      return;
    }
    if (frequency === "once" && !runAt) {
      setError("请选择一次性任务的时间");
      return;
    }
    if (frequency === "interval" && (!intervalMinutes || intervalMinutes < 1)) {
      setError("请填写有效的间隔分钟数");
      return;
    }
    if (frequency === "weekly" && daysOfWeek.length === 0) {
      setError("请至少选择一天");
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
        payload.day_of_month = dayOfMonth;
      }
      if (frequency !== "once") {
        payload.run_hour = runHour;
        payload.run_minute = runMinute;
      }
      if (task) {
        await updateScheduledTask(task.id, payload);
      } else {
        await createScheduledTask(payload);
      }
      await onSaved();
      toast.success(task ? "定时任务已更新" : "定时任务已创建");
    } catch (error) {
      setError(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      title={task ? "编辑定时任务" : "新建定时任务"}
      onClose={onClose}
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            取消
          </Button>
          <Button
            variant="primary"
            loading={saving}
            onClick={() => void handleSave()}
          >
            保存
          </Button>
        </>
      }
    >
      <div className="scheduled-form">
        <Input
          label="标题"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="例如：买机票"
        />
        <Input
          label="描述"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="提醒内容或任务描述"
        />
        <Select
          label="频率"
          value={frequency}
          onChange={(value) =>
            setFrequency(value as ScheduledTask["frequency"])
          }
          options={[
            { value: "once", label: "一次性" },
            { value: "interval", label: "每隔 x 分钟" },
            { value: "daily", label: "每天" },
            { value: "weekly", label: "每周" },
            { value: "monthly", label: "每月" },
          ]}
        />
        {frequency === "once" && (
          <DateTimePicker
            label="时间"
            value={runAt}
            onChange={setRunAt}
          />
        )}
        {frequency === "interval" && (
          <Input
            label="间隔（分钟）"
            type="text"
            inputMode="numeric"
            value={intervalMinutes}
            onChange={(event) => {
              const digits = event.target.value.replace(/\D/g, "");
              setIntervalMinutes(digits === "" ? 1 : Number(digits));
            }}
          />
        )}
        {frequency !== "once" && frequency !== "interval" && (
          <>
            <Input
              label="小时（每天的几点）"
              type="text"
              inputMode="numeric"
              value={runHour}
              onChange={(event) => {
                const digits = event.target.value.replace(/\D/g, "");
                setRunHour(digits === "" ? 0 : Math.min(23, Number(digits)));
              }}
            />
            <Input
              label="分钟（几点几分）"
              type="text"
              inputMode="numeric"
              value={runMinute}
              onChange={(event) => {
                const digits = event.target.value.replace(/\D/g, "");
                setRunMinute(digits === "" ? 0 : Math.min(59, Number(digits)));
              }}
            />
          </>
        )}
        {frequency === "weekly" && (
          <div className="ui-field">
            <span className="ui-field-label">每周</span>
            <Flex gap={6} wrap className="weekday-picker">
              {WEEKDAYS.map((label, day) => (
                <button
                  key={label}
                  type="button"
                  className={daysOfWeek.includes(day) ? "active" : ""}
                  onClick={() => toggleDay(day)}
                >
                  {label}
                </button>
              ))}
            </Flex>
          </div>
        )}
        {frequency === "monthly" && (
          <Input
            label="每月日期"
            type="text"
            inputMode="numeric"
            value={dayOfMonth}
            onChange={(event) => {
              const digits = event.target.value.replace(/\D/g, "");
              setDayOfMonth(
                digits === "" ? 1 : Math.min(31, Number(digits))
              );
            }}
          />
        )}
        {error && <div className="scheduled-form-error">{error}</div>}
      </div>
    </Modal>
  );
}
