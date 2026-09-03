// JS 侧图表/流程图基色，与 styles/index.less 的 CSS token 对齐。
// 同步源：divine-app/src/styles/index.less 的 :root / :root[data-theme="light"]。
// 需要改正文/表面色时，改 index.less 一处即可，Chart 与 Mermaid 跟随此文件。
// 注意：rgba 边框、tooltip 透明底等 JS 专属值不在此列，留在各自文件。

export const UI_COLORS = {
  dark: {
    bg: "#0b0d0f", // --color-bg
    surface: "#121517", // --color-surface
    surface2: "#171b1f", // --color-surface-2
    codeBg: "#0d1013", // --color-code-bg
    text: "#f2f4f6", // --color-text
    textSecondary: "#a4adba", // --color-text-secondary
    textMuted: "#6f7783", // --color-text-muted
  },
  light: {
    bg: "#f6f7f9", // --color-bg
    surface: "#ffffff", // --color-surface
    surface2: "#eef1f4", // --color-surface-2
    codeBg: "#f2f4f7", // --color-code-bg
    text: "#1f2937", // --color-text
    textSecondary: "#5b6472", // --color-text-secondary
    textMuted: "#8a94a3", // --color-text-muted
  },
} as const;

export type UITheme = keyof typeof UI_COLORS;
