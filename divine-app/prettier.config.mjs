// 保留项目既有风格（双引号 + 分号），避免全量格式化污染业务 diff；
// 行宽 100 与现存代码一致。格式类规则由 eslint-config-prettier 关闭，
// ESLint 只管代码质量，Prettier 只管格式（职责分离）。
/** @type {import("prettier").Config} */
export default {
  printWidth: 100,
  semi: true,
  singleQuote: false,
  endOfLine: "lf",
};
