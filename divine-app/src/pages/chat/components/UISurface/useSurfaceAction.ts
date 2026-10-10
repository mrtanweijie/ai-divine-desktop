/**
 * 面板动作回流：把「用户点了某个按钮」变成一次新的对话回合。
 *
 * 设计文档：`docs/design/028-a2ui-integration-20261009.md` §8。
 *
 * 关键约束（044 §8.2 / §5.5）：
 * - 动作**不是**特权通道：它等价于"用户说了一句话"，复用 `/stream_chat` 管线，
 *   因此 agent 内核零侵入（不碰 interrupt / 配置中间件）。
 * - 请求体必须带 `data_model`（面板当前态）与 `context`（求值后的动作上下文），
 *   因为 `message_parts` **不进模型上下文**，后端会把求值结果写进可见正文。
 * - `action_id` 是幂等键（60s 内重复只跑一轮），前端连点两次不会跑两遍。
 * - 失败**回滚**：只弹 toast，不改本地数据（面板状态仍以用户输入为准）。
 *
 * **提交必须走聊天上下文，不能在这里直接 fetch**：后端返回的是 SSE 流
 * （动作会跑出一整个新回合、可能再吐一块面板），只有 `useChatStream` 那套
 * 处理器能把流消费掉并让面板"原地刷新"。这里只负责收集参数与展示结果。
 */

import { useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { toast } from "@/components/ui/Toast";
import { useOptionalChatStreamContext } from "@/pages/chat/hooks/ChatStreamContext";
import { getByPath, isBinding } from "./dataModel";
import type { UIAction, UIActionContextItem } from "./types";

/** 生成幂等键。优先用 crypto.randomUUID（Tauri/现代浏览器都有）。 */
function makeActionId(): string {
  const uuid =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  return `act_${uuid}`;
}

/**
 * 求值动作上下文：`[{key, value}]` → `{key: 求值结果}`。
 * `value` 可以是字面量，也可以是 `{path}`（面板里改过的值）。
 */
export function evaluateActionContext(
  items: UIActionContextItem[] | undefined,
  dataModel: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const item of items ?? []) {
    if (!item || typeof item.key !== "string") continue;
    out[item.key] = isBinding(item.value) ? getByPath(dataModel, item.value.path) : item.value;
  }
  return out;
}

/** 提交失败的三种原因各自说一句准确的话（不重试、不排队，重试=用户再点一次）。 */
function failureText(reason: "busy" | "disabled" | "failed", t: TFunction): string {
  if (reason === "busy") {
    return t("uiSurface.sessionBusy", "当前会话正在生成中，请等这轮结束后再操作");
  }
  if (reason === "disabled") {
    return t("uiSurface.disabled", "交互面板当前不可用");
  }
  return t("uiSurface.actionFailed", "操作提交失败，请重试");
}

interface UseSurfaceActionOptions {
  surfaceId: string;
  sessionId?: string | null;
  messageId?: string;
  /** 读最新的 dataModel（面板当前态）。用 getter 而非值，避免闭包拿到旧快照。 */
  getDataModel: () => Record<string, unknown>;
  /** 当有动作在提交中时通知外层（用于按钮 loading / 全禁）。 */
  onPendingChange?: (componentId: string | null) => void;
  /** 回合已被受理（§8.3：此刻清掉该面板的用户编辑态）。 */
  onAccepted?: () => void;
}

/** 面板动作提交。返回的 `submit` 引用稳定。 */
export function useSurfaceAction(options: UseSurfaceActionOptions): {
  submit: (action: UIAction, componentId: string, label?: string) => void;
} {
  const { t } = useTranslation();
  const chatStream = useOptionalChatStreamContext();
  // 用 ref 拿最新的 context：provider 的 value 会随输入框档位变化重建，
  // 不能让 `submit` 的引用跟着变（它是 SurfaceContext 的一部分，变了会
  // 让整块面板重渲染）。
  const chatStreamRef = useRef(chatStream);
  const optionsRef = useRef(options);
  // 用 effect 同步「最新值」，**不能**在 render 期直接给 ref.current 赋值：
  // render 必须是纯的（React 明确禁止，react-hooks/refs 会报错）。事件回调
  // 总发生在 commit 之后，所以这里同步的值对 `submit` 而言一定是最新的。
  useEffect(() => {
    chatStreamRef.current = chatStream;
    optionsRef.current = options;
  });
  const inFlight = useRef(false);

  const submit = useCallback(
    (action: UIAction, componentId: string, label?: string) => {
      const current = optionsRef.current;
      if (inFlight.current) return;
      if (!current.sessionId) return;
      if (!action || typeof action.name !== "string" || !action.name) return;
      // 没有聊天上下文（离线样张 / 组件测试里单独渲染面板）：静默无效，
      // 好过整块崩掉 —— 面板本身仍应能正常显示。
      const stream = chatStreamRef.current;
      if (!stream) return;

      const dataModel = current.getDataModel();
      const actionId = makeActionId();
      inFlight.current = true;
      current.onPendingChange?.(componentId);

      void stream
        .submitSurfaceAction(
          {
            sessionId: current.sessionId,
            messageId: current.messageId ?? "",
            surfaceId: current.surfaceId,
            actionId,
            name: action.name,
            label: label ?? "",
            context: evaluateActionContext(action.context, dataModel),
            dataModel,
          },
          { onAccepted: () => current.onAccepted?.() },
        )
        .then((result) => {
          if (!result.ok) {
            // 失败不改本地状态：面板仍是用户填的那份，重试即可。
            toast.error(failureText(result.reason, t));
          }
        })
        .catch((error: unknown) => {
          toast.error(t("uiSurface.actionFailed", "操作提交失败，请重试"));
          console.error("[uiSurface] surface-action failed", error);
        })
        .finally(() => {
          inFlight.current = false;
          optionsRef.current.onPendingChange?.(null);
        });
    },
    [t],
  );

  return { submit };
}
