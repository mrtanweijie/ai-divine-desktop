import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { DateTimePicker } from "@/components/ui/DateTimePicker";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { TextArea } from "@/components/ui/TextArea";
import { toast } from "@/components/ui/Toast";
import { createScheduledTask, updateScheduledTask } from "@/services/scheduledTasks";
import type { DeliveryConfig, ScheduledTask, ScheduledTaskType } from "@/types";
import { ChannelEditor } from "./ChannelEditor";
import { CollapsibleSection } from "./CollapsibleSection";
import { weekdayLabels, toLocalInputValue } from "../scheduleUtils";
import "./TaskModal.less";

interface TaskModalProps {
  task?: ScheduledTask;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

/**
 * 任务类型**不暴露给用户选**——由「填了什么」推导。
 *
 * 配了推送通道 → webhook（跑完把结果推出去）；
 * 只填了提示词   → agent（只跑，不推）；
 * 都空           → reminder（只提醒，不跑 Agent）。
 */
function deriveTaskType(input: { hasChannels: boolean; hasPrompt: boolean }): ScheduledTaskType {
  if (input.hasChannels) return "webhook";
  if (input.hasPrompt) return "agent";
  return "reminder";
}

export function TaskModal({ task, onClose, onSaved }: TaskModalProps) {
  const { t } = useTranslation();
  // 旧 reminder 只有 description、没有 prompt——一并带进来，
  // 否则打开编辑框会看到空白，像是数据丢了。
  const [prompt, setPrompt] = useState(task?.prompt || task?.description || "");
  const [delivery, setDelivery] = useState<DeliveryConfig>(
    task?.delivery ?? task?.delivery_json ?? { channels: [] },
  );
  const [title, setTitle] = useState(task?.title ?? "");
  const [frequency, setFrequency] = useState<ScheduledTask["frequency"]>(task?.frequency ?? "once");
  const [runAt, setRunAt] = useState(toLocalInputValue(task?.run_at));
  const [intervalMinutes, setIntervalMinutes] = useState<number | null>(
    task?.interval_minutes ?? 60,
  );
  const [runHour, setRunHour] = useState<number | null>(task?.run_hour ?? 8);
  const [runMinute, setRunMinute] = useState<number | null>(task?.run_minute ?? 0);
  const [daysOfWeek, setDaysOfWeek] = useState<number[]>(task?.days_of_week ?? []);
  const [dayOfMonth, setDayOfMonth] = useState<number | null>(task?.day_of_month ?? 1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleDay = (day: number) => {
    setDaysOfWeek((prev) =>
      prev.includes(day) ? prev.filter((item) => item !== day) : [...prev, day],
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
    if (frequency === "interval" && (intervalMinutes === null || intervalMinutes < 1)) {
      setError(t("tasks.intervalRequired", "请填写有效的间隔分钟数"));
      return;
    }
    if (frequency === "weekly" && daysOfWeek.length === 0) {
      setError(t("tasks.weekdayRequired", "请至少选择一天"));
      return;
    }
    const channels = delivery.channels ?? [];
    const taskType = deriveTaskType({
      hasChannels: channels.length > 0,
      hasPrompt: Boolean(prompt.trim()),
    });
    // 只要不是纯提醒，就得知道让 Agent 干什么
    if (taskType !== "reminder" && !prompt.trim()) {
      setError(t("tasks.promptRequired", "请填写任务提示词"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload: Partial<ScheduledTask> & { title: string } = {
        title: title.trim(),
        // description 与 prompt 合一：一个输入框，存两份（TaskRow 展示用 description）
        description: prompt.trim(),
        frequency,
        task_type: taskType,
        prompt: prompt.trim(),
        // 定时任务无人值守：若沿用 session 的 ask 模式，Agent 会在首个工具调用处
        // 等一个永远不会到来的人工确认，任务等于卡死。所以这里固定给完全访问。
        allow_full_access: true,
        // 空数组 = 不推送；编辑时也回传，保证表单能原样带回来
        delivery,
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
        task ? t("tasks.taskUpdated", "定时任务已更新") : t("tasks.taskCreated", "定时任务已创建"),
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : t("tasks.saveFailed", "保存失败"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      title={task ? t("tasks.editTitle", "编辑定时任务") : t("tasks.createTitle", "新建定时任务")}
      onClose={onClose}
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel", "取消")}
          </Button>
          <Button variant="primary" loading={saving} onClick={() => void handleSave()}>
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
        <TextArea
          label={t("tasks.promptLabel", "任务提示词")}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={4}
          placeholder={t(
            "tasks.promptPlaceholder",
            "例如：收集近 24 小时 AI 领域的重要新闻，整理成三条要点；留空则只提醒、不执行",
          )}
        />
        <CollapsibleSection
          title={t("tasks.deliveryLabel", "推送到")}
          hint={
            (delivery.channels ?? []).length > 0
              ? t("tasks.channelCount", "已配置 {{count}} 个通道", {
                  count: (delivery.channels ?? []).length,
                })
              : t("tasks.noChannel", "未配置投递通道（任务仍会执行，只是不推送）")
          }
          defaultOpen={(delivery.channels ?? []).length > 0}
        >
          <ChannelEditor value={delivery} onChange={setDelivery} />
        </CollapsibleSection>
        {/* 时间参数与频率横排：频率定宽，其余填充剩余空间 */}
        <Flex gap={10} align="flex-start" wrap className="task-frequency-row">
          <Select
            label={t("tasks.frequencyLabel", "频率")}
            value={frequency}
            onChange={(value) => setFrequency(value as ScheduledTask["frequency"])}
            options={[
              { value: "once", label: t("tasks.frequencyOnce", "一次性") },
              { value: "interval", label: t("tasks.frequencyInterval", "每隔 x 分钟") },
              { value: "daily", label: t("tasks.frequencyDaily", "每天") },
              { value: "weekly", label: t("tasks.frequencyWeekly", "每周") },
              { value: "monthly", label: t("tasks.frequencyMonthly", "每月") },
            ]}
          />
          {frequency === "once" && (
            <DateTimePicker label={t("time.label", "时间")} value={runAt} onChange={setRunAt} />
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
          {frequency === "monthly" && (
            <Input
              label={t("tasks.monthlyDate", "每月几号")}
              type="text"
              inputMode="numeric"
              value={dayOfMonth ?? ""}
              onChange={(event) => {
                const digits = event.target.value.replace(/\D/g, "");
                setDayOfMonth(digits === "" ? null : Math.min(31, Number(digits)));
              }}
            />
          )}
          {frequency !== "once" && frequency !== "interval" && (
            <>
              <Input
                label={t("tasks.hourLabel", "小时")}
                type="text"
                inputMode="numeric"
                value={runHour ?? ""}
                onChange={(event) => {
                  const digits = event.target.value.replace(/\D/g, "");
                  setRunHour(digits === "" ? null : Math.min(23, Number(digits)));
                }}
              />
              <Input
                label={t("tasks.minuteLabel", "分钟")}
                type="text"
                inputMode="numeric"
                value={runMinute ?? ""}
                onChange={(event) => {
                  const digits = event.target.value.replace(/\D/g, "");
                  setRunMinute(digits === "" ? null : Math.min(59, Number(digits)));
                }}
              />
            </>
          )}
        </Flex>
        {frequency === "weekly" && (
          <div className="ui-field">
            <span className="ui-field-label">{t("tasks.frequencyWeekly", "每周")}</span>
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
        {error && <div className="scheduled-form-error">{error}</div>}
      </div>
    </Modal>
  );
}
