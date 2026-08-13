import { defineConfig } from "i18next-cli";

export default defineConfig({
  locales: ["zh-CN", "zh-TW", "en"],
  extract: {
    input: ["src/**/*.{ts,tsx}"],
    output: "src/i18n/locales/{{language}}/{{namespace}}.json",
    defaultNS: "translation",
    primaryLanguage: "zh-CN",
  },
});
