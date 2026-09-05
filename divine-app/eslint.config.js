// ESLint 平面配置（eslint 9/10 flat config）。
// 质量闸分工：tsc -b 管类型，eslint 管hooks 规则/未使用代码/显式 any 等。
// 运行：pnpm lint（检查）/ pnpm lint:fix（自动修复）。
import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";
import eslintConfigPrettier from "eslint-config-prettier";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "node_modules",
      "src-tauri",
      // vendored Grok Ball 引擎：头部 @ts-nocheck 的第三方代码，不参与 lint
      "src/pages/chat/components/NewChatGuide/DivineBall.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      globals: { ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // 采纳期策略：存量问题先降为警告，后续逐步清零
      "@typescript-eslint/no-explicit-any": "warn", // 存量 ~9 处
      "@typescript-eslint/no-non-null-assertion": "warn", // 存量 2 处
      // react-hooks v7 编译器衍生新规则与现有模式（模块级单例 store、
      // 挂载期数据加载）系统性冲突，共 ~34 处；重构是独立任务，先降为警告
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/immutability": "warn",
      "react-hooks/use-memo": "warn",
      "react-hooks/static-components": "warn",
      "react-hooks/incompatible-library": "warn",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
  eslintConfigPrettier,
);
