import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { STORAGE_KEYS } from "@/constant/storage";
import { storageGetRaw, storageSetRaw } from "@/services/storage";
import en from "./locales/en/translation.json";
import zhCN from "./locales/zh-CN/translation.json";
import zhTW from "./locales/zh-TW/translation.json";

export const LOCALES = ["zh-CN", "zh-TW", "en"] as const;
export type AppLocale = (typeof LOCALES)[number];

export function readLocalePreference(): AppLocale {
  const value = storageGetRaw(STORAGE_KEYS.locale);
  return (LOCALES as readonly string[]).includes(value ?? "")
    ? (value as AppLocale)
    : "zh-CN";
}

export function setLocale(locale: AppLocale): void {
  storageSetRaw(STORAGE_KEYS.locale, locale);
  document.documentElement.lang = locale;
  void i18n.changeLanguage(locale);
}

void i18n.use(initReactI18next).init({
  resources: {
    "zh-CN": { translation: zhCN },
    "zh-TW": { translation: zhTW },
    en: { translation: en },
  },
  lng: readLocalePreference(),
  fallbackLng: {
    "zh-TW": ["zh-TW", "zh-CN", "en"],
    default: ["zh-CN", "en"],
  },
  interpolation: { escapeValue: false },
});

document.documentElement.lang = readLocalePreference();

export default i18n;
