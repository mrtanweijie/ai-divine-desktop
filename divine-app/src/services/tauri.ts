import { invoke } from "@tauri-apps/api/core";

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function isMacosDesktop(): boolean {
  if (!isTauri() || typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad/.test(navigator.platform ?? "");
}

export async function openLocalFile(path: string): Promise<void> {
  await invoke("open_local_file", { path });
}

export async function openFileLocation(path: string): Promise<void> {
  await invoke("open_file_location", { path });
}

export async function openUrl(url: string): Promise<void> {
  await invoke("open_url", { url });
}
