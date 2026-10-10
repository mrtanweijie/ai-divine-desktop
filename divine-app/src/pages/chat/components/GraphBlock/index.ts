/**
 * GraphBlock 目录入口。
 *
 * 目录对外只暴露**容器组件**与少量公共类型；渲染器、形态表、预设表等实现
 * 细节不在这里 re-export，避免外部绕过容器直接依赖内部模块。
 */

export { GraphBlock } from "./GraphBlock";
export type { GraphIR, GraphKind, GraphNode } from "./GraphIR";
// 画布最小高度是容器**初始占位**高度。A2UI 面板做懒挂载时要按同一数值预留，
// 否则懒挂载前后等高不成立，会重新引入虚拟列表高度抖动（028 §16.4）。
export { CANVAS_MIN_HEIGHT } from "./GraphRenderer";
