import { useEffect, useState } from "react";
import { STORAGE_KEYS } from "@/constant/storage";
import { storageGetRaw, storageSetRaw } from "@/services/storage";

export type ThemePreference = "dark" | "light" | "system";
export type ResolvedTheme = "dark" | "light";

const THEME_EVENT = "divine:theme-change";

function systemTheme(): ResolvedTheme {
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

export function readThemePreference(): ThemePreference {
  const value = storageGetRaw(STORAGE_KEYS.theme);
  return value === "dark" || value === "light" || value === "system"
    ? value
    : "system";
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  return preference === "system" ? systemTheme() : preference;
}

export function applyTheme(preference: ThemePreference): void {
  document.documentElement.dataset.theme = resolveTheme(preference);
}

export function setThemePreference(preference: ThemePreference): void {
  storageSetRaw(STORAGE_KEYS.theme, preference);
  applyTheme(preference);
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: preference }));
}

export function initTheme(): void {
  applyTheme(readThemePreference());
  const media = window.matchMedia("(prefers-color-scheme: light)");
  const handleSystemChange = () => {
    if (readThemePreference() === "system") {
      applyTheme("system");
      window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: "system" }));
    }
  };
  media.addEventListener("change", handleSystemChange);
}

export function useTheme(): ResolvedTheme {
  const [theme, setTheme] = useState<ResolvedTheme>(() =>
    resolveTheme(readThemePreference())
  );

  useEffect(() => {
    const sync = () => setTheme(resolveTheme(readThemePreference()));
    const media = window.matchMedia("(prefers-color-scheme: light)");
    window.addEventListener(THEME_EVENT, sync);
    media.addEventListener("change", sync);
    return () => {
      window.removeEventListener(THEME_EVENT, sync);
      media.removeEventListener("change", sync);
    };
  }, []);

  return theme;
}

export function useThemePreference(): [
  ThemePreference,
  (preference: ThemePreference) => void,
] {
  const [preference, setPreference] = useState<ThemePreference>(
    readThemePreference
  );

  useEffect(() => {
    const sync = () => setPreference(readThemePreference());
    window.addEventListener(THEME_EVENT, sync);
    return () => window.removeEventListener(THEME_EVENT, sync);
  }, []);

  return [
    preference,
    (next) => {
      setThemePreference(next);
      setPreference(next);
    },
  ];
}
