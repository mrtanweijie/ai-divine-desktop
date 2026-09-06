import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { FileDiff, WorkspaceFileNode } from "@/types";

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

export async function openFolder(path: string): Promise<void> {
  await invoke("open_folder", { path });
}

export async function openUrl(url: string): Promise<void> {
  await invoke("open_url", { url });
}

export async function setGlobalShortcutEnabled(enabled: boolean): Promise<void> {
  await invoke("set_global_shortcut_enabled", { enabled });
}

export async function getAppVersion(): Promise<string> {
  if (!isTauri()) return "";
  try {
    const { getVersion } = await import("@tauri-apps/api/app");
    return await getVersion();
  } catch {
    return "";
  }
}

export async function savePasteText(
  text: string,
): Promise<{ name: string; path: string; size: number; hash: string }> {
  return invoke("save_paste_text", { text });
}

export async function savePasteImage(
  base64: string,
  mime: string,
): Promise<{ name: string; path: string; size: number }> {
  return invoke("save_paste_image", { base64, mime });
}

export async function savePasteFile(
  base64: string,
  name: string,
): Promise<{ name: string; path: string; size: number }> {
  return invoke("save_paste_file", { base64, name });
}

/** 把图表导出字节（base64，无 data: 前缀）写入 <workspace>/charts/，返回落盘路径 */
export async function saveExportFile(
  workspace: string,
  base64: string,
  name: string,
): Promise<{ name: string; path: string; size: number }> {
  return invoke("save_export_file", { workspace, base64, name });
}

export async function getExternalFilePreview(path: string): Promise<FileDiff> {
  return invoke("get_external_file_preview", { path });
}

export async function getBinaryPreview(path: string): Promise<{ mime: string; dataUrl: string }> {
  return invoke("get_binary_preview", { path });
}

export async function getFileTree(root: string): Promise<WorkspaceFileNode[]> {
  return invoke("get_file_tree", { root });
}

export async function getDirChildren(root: string, dir: string): Promise<WorkspaceFileNode[]> {
  return invoke("get_dir_children", { root, dir });
}

export async function getFileDiff(repoPath: string, relPath: string): Promise<FileDiff> {
  return invoke("get_file_diff", { repoPath, relPath });
}

export async function watchWorkspace(path: string): Promise<void> {
  await invoke("watch_workspace", { path });
}

export async function unwatchWorkspace(path: string): Promise<void> {
  await invoke("unwatch_workspace", { path });
}

export async function listenWorkspaceChanges(
  callback: (payload: { path: string; kind: string }) => void,
): Promise<UnlistenFn> {
  return listen("workspace:changed", (event) => {
    callback(event.payload as { path: string; kind: string });
  });
}
