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

import { useCallback, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { resolveBindable, setByPath } from "./dataModel";
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
}

export function UISurfaceBlock({ surface, sessionId, workspacePath }: UISurfaceBlockProps) {
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

  const { submit } = useSurfaceAction({
    surfaceId: surface.surfaceId,
    sessionId,
    messageId: surface.messageId,
    getDataModel,
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

  const ctx: SurfaceContext = {
    data: dataModel,
    setValue,
    submit,
    status: surface.status,
    pendingActionId: pendingComponentId,
    resolve,
    renderChild,
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
    </section>
  );
}
