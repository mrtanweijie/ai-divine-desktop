/**
 * 面板渲染根：持有 dataModel 状态、组装 SurfaceContext、递归渲染组件树。
 *
 * 设计文档：`docs/design/028-a2ui-integration-20261009.md` §5.2 / §7 / §16。
 *
 * 三条性能约定（044 §16，改这里前先读那节）：
 * 1. **原子渲染**：一整块 surface 一次成型，不做渐进（§5.1 帧内完整性）。
 * 2. **高度稳定**：容器 `contain: layout paint style`，内部可变高度组件
 *    （Image 的 aspect-ratio、Table 的 maxHeight）必须自留高度，防虚拟列表抖动。
 * 3. **引用稳定**：`surfaces` 数组由 surfaceStore 保证「seq 不变则引用不变」，
 *    本组件不额外制造新数组（否则 MessageItem 的 memo 会失效）。
 *
 * 重新挂载约定：外层用 `key={surfaceId:seq}` 挂载，`seq` 变化即整块重挂载
 * （= §8.3 的"面板原地刷新"），因此 dataModel 不需要在 effect 里同步。
 */

import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Loader2 } from "lucide-react";
import { ChoiceBlock, splitNoteOptions } from "@/pages/chat/components/ChoiceBlock";
import { collectInputBindings, resolveBindable, setByPath } from "./dataModel";
import { renderComponentNode } from "./registry";
import { applyEditsToDataModel, clearSurfaceEdits, writeSurfaceEdit } from "./uiSurfaceStateStore";
import { useSurfaceAction } from "./useSurfaceAction";
import type { SurfaceContext, UIBindable, UISurface } from "./types";
import "./UISurface.less";

interface UISurfaceBlockProps {
  surface: UISurface;
  sessionId?: string | null;
  /** 当前会话工作区路径（只服务 Chart/Graph 导出与 FileList 定位）。 */
  workspacePath?: string | null;
  /** 面板动作提交中（消息级本地流态，见 types.ts）。 */
  updating?: boolean;
  /** 面板动作这一轮出错（消息级本地流态）。 */
  error?: string;
  /** 上一次面板动作的结果说明（后端 surface_note part）。 */
  note?: { text: string; updated: boolean };
}

/** 面板底部状态行：更新中 / 更新失败 / 本轮结果说明（design 028 §8.5）。 */
function SurfaceFooter({
  updating,
  error,
  note,
}: {
  updating?: boolean;
  error?: string;
  note?: { text: string; updated: boolean };
}) {
  const { t } = useTranslation();
  // 本轮正文里可能带 ```options 围栏：拆开后说明行只显示散文，选项渲染成可点
  // 卡片（见 splitNoteOptions）。注意必须放在下面所有 early return 之前 ——
  // hooks 不能出现在条件分支之后。
  const { prose, data } = useMemo(() => splitNoteOptions(note?.text ?? ""), [note?.text]);
  if (updating) {
    return (
      <footer className="uis-footer is-busy">
        <Loader2 size={13} className="uis-footer-spinner" />
        <span>{t("uiSurface.updating", "正在更新面板…")}</span>
      </footer>
    );
  }
  if (error) {
    return (
      <footer className="uis-footer is-error">
        <AlertCircle size={13} />
        <span>{t("uiSurface.updateFailed", "面板更新失败")}</span>
        <span className="uis-footer-detail">{error}</span>
      </footer>
    );
  }
  if (!note) return null;
  // 选项卡**不传 messageId**：一条消息只有一个 choice_state 槽
  // （saveMessageChoiceState 按消息覆盖），而承载消息自身可能已有顶层选项卡，
  // 共用一个槽会互相污染——刷新后两张卡片显示同一个选中项。
  // 代价是本卡片的选中态不落库、刷新后回到未选，可接受（028 §8.5）。
  const choice = data ? (
    <div className="uis-footer-choice">
      <ChoiceBlock data={data} />
    </div>
  ) : null;
  // 这一轮模型只说了话、没返回面板：必须说出来，否则用户以为"点了没反应"。
  if (!note.updated) {
    return (
      <>
        <footer className="uis-footer is-stale">
          <AlertCircle size={13} />
          <span>{t("uiSurface.noUpdate", "本轮未返回面板更新")}</span>
          {prose ? <span className="uis-footer-detail">{prose}</span> : null}
        </footer>
        {choice}
      </>
    );
  }
  if (!prose && !choice) return null;
  return (
    <>
      {prose ? (
        <footer className="uis-footer">
          <span className="uis-footer-detail">{prose}</span>
        </footer>
      ) : null}
      {choice}
    </>
  );
}

export function UISurfaceBlock({
  surface,
  sessionId,
  workspacePath,
  updating,
  error,
  note,
}: UISurfaceBlockProps) {
  const { t } = useTranslation();
  // 初始值叠加"编辑态"（模块级 Map 里的未提交改动），实现"滚出去再滚回来输入还在"。
  // `closed` 是历史快照（含刚被新一轮覆盖下来的旧面板），**不叠加** ——
  // 未提交的编辑值不该污染"面板当时长什么样"的归档（044 §5.5 硬约束 1）。
  const [dataModel, setDataModel] = useState<Record<string, unknown>>(() =>
    surface.status === "live"
      ? applyEditsToDataModel(sessionId, surface.surfaceId, surface.dataModel)
      : surface.dataModel,
  );
  // 与 state 同步维护的最新快照：动作提交时读它，避免闭包拿到旧 dataModel。
  const dataModelRef = useRef<Record<string, unknown>>(dataModel);
  const [pendingComponentId, setPendingComponentId] = useState<string | null>(null);

  const setValue = useCallback(
    (path: string, value: unknown) => {
      setDataModel((prev) => {
        const next = setByPath(prev, path, value);
        dataModelRef.current = next;
        return next;
      });
      // 记进模块级 Map（零延迟）+ 防抖落 DB（抗刷新）。见 uiSurfaceStateStore。
      writeSurfaceEdit(sessionId, surface.surfaceId, path, value, surface.messageId);
    },
    [sessionId, surface.messageId, surface.surfaceId],
  );

  const getDataModel = useCallback(() => dataModelRef.current, []);

  // 输入控件绑定：动作提交时用它兜底回传用户填的值（模型常漏写 action.context）。
  // 只依赖 surface（IR 不变则引用不变），不依赖 dataModel —— 路径集合与值无关。
  const inputBindings = useMemo(() => collectInputBindings(surface), [surface]);

  const { submit } = useSurfaceAction({
    surfaceId: surface.surfaceId,
    sessionId,
    messageId: surface.messageId,
    getDataModel,
    inputs: inputBindings,
    onPendingChange: setPendingComponentId,
    // 回合一被受理就清编辑态（§8.3）：面板已被新一轮覆盖，旧编辑态不再有意义。
    // 不能等流结束——新面板挂载时会先把旧编辑态叠加一遍。
    onAccepted: () => clearSurfaceEdits(sessionId, surface.surfaceId),
  });

  const resolve = useCallback(
    <T,>(value: UIBindable<T> | undefined): T | undefined => resolveBindable<T>(dataModel, value),
    [dataModel],
  );

  // renderChild 在函数体内自引用 ctx：调用发生在 ctx 赋值之后，是安全的闭包。
  const renderChild = (id: string): ReactNode => {
    const component = surface.components[id];
    if (!component) return null;
    return renderComponentNode(component.component, component, ctx);
  };

  // 只读的组件定义查询（容器判断子项类型用）；IR 不变则引用不变。
  const getComponent = useCallback((id: string) => surface.components[id], [surface]);

  const ctx: SurfaceContext = {
    data: dataModel,
    setValue,
    submit,
    status: surface.status,
    pendingActionId: pendingComponentId,
    resolve,
    renderChild,
    getComponent,
    workspacePath,
  };

  const root = surface.components[surface.rootId];

  return (
    <section
      className={`uis-surface${surface.status === "closed" ? " is-closed" : ""}`}
      data-surface-id={surface.surfaceId}
      aria-label={surface.title ?? t("uiSurface.panel", "交互面板")}
    >
      {surface.title ? (
        <header className="uis-header">
          <span className="uis-header-title">{surface.title}</span>
          {surface.status === "closed" ? (
            <span className="uis-header-badge">{t("uiSurface.closed", "历史面板")}</span>
          ) : null}
        </header>
      ) : null}
      <div className="uis-body">
        {root ? (
          renderComponentNode(root.component, root, ctx)
        ) : (
          <div className="uis-empty">{t("uiSurface.unavailable", "面板内容不可用")}</div>
        )}
      </div>
      <SurfaceFooter updating={updating} error={error} note={note} />
    </section>
  );
}
