/**
 * GraphBlock 目录入口。
 *
 * 目录对外只暴露**容器组件**与少量公共类型；渲染器、形态表、预设表等实现
 * 细节不在这里 re-export，避免外部绕过容器直接依赖内部模块。
 */

export { GraphBlock } from "./GraphBlock";
export type { GraphIR, GraphKind, GraphNode } from "./GraphIR";
