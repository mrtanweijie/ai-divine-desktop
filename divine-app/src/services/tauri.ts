export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function isMacosDesktop(): boolean {
  if (!isTauri() || typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad/.test(navigator.platform ?? "");
}
