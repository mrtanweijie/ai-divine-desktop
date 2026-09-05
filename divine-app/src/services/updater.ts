import { useSyncExternalStore } from "react";
import { check, type DownloadEvent, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { isTauri } from "@/services/tauri";

export type UpdaterStatus =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "downloaded"
  | "uptodate"
  | "error"
  | "disabled";

export interface UpdaterState {
  status: UpdaterStatus;
  version: string;
  body: string;
  progress: number;
  message: string;
  update: Update | null;
  bannerDismissed: boolean;
  dismissedVersion: string;
}

const initialState: UpdaterState = {
  status: "idle",
  version: "",
  body: "",
  progress: 0,
  message: "",
  update: null,
  bannerDismissed: false,
  dismissedVersion: "",
};

let state = initialState;
let currentUpdate: Update | null = null;
const listeners = new Set<() => void>();
const settingsListeners = new Set<() => void>();
let autoStarted = false;
let busy = false;
let settingsOpen = false;

function setState(patch: Partial<UpdaterState>) {
  state = { ...state, ...patch };
  listeners.forEach((callback) => callback());
}

export function subscribeUpdater(callback: () => void): () => void {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

export function getUpdaterState(): UpdaterState {
  return state;
}

export function useUpdaterState(): UpdaterState {
  return useSyncExternalStore(subscribeUpdater, getUpdaterState);
}

function subscribeSettingsOpen(callback: () => void): () => void {
  settingsListeners.add(callback);
  return () => settingsListeners.delete(callback);
}

function getSettingsOpen(): boolean {
  return settingsOpen;
}

export function useSettingsOpen(): boolean {
  return useSyncExternalStore(subscribeSettingsOpen, getSettingsOpen);
}

export function setSettingsOpen(open: boolean): void {
  if (settingsOpen === open) return;
  settingsOpen = open;
  settingsListeners.forEach((callback) => callback());
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error);
}

export async function checkForUpdates(): Promise<void> {
  if (!isTauri()) {
    setState({ ...initialState, status: "disabled" });
    return;
  }
  if (busy) return;
  busy = true;
  setState({ ...state, status: "checking", progress: 0, message: "" });
  try {
    const found = await check({ timeout: 30_000 });
    currentUpdate = found;
    if (found) {
      const sameDismissed = state.bannerDismissed && state.dismissedVersion === found.version;
      setState({
        status: "available",
        version: found.version,
        body: found.body ?? "",
        progress: 0,
        message: "",
        update: found,
        bannerDismissed: sameDismissed,
        dismissedVersion: found.version,
      });
    } else {
      setState({
        status: "uptodate",
        version: "",
        body: "",
        progress: 0,
        message: "",
        update: null,
        bannerDismissed: false,
        dismissedVersion: "",
      });
    }
  } catch (error) {
    currentUpdate = null;
    setState({
      status: "error",
      version: "",
      body: "",
      progress: 0,
      message: errorMessage(error),
      update: null,
      bannerDismissed: false,
      dismissedVersion: "",
    });
  } finally {
    busy = false;
  }
}

export async function downloadAndInstallUpdate(): Promise<void> {
  const target = currentUpdate;
  if (!isTauri() || !target || busy) return;
  busy = true;
  setState({
    status: "downloading",
    version: target.version,
    progress: 0,
    message: "",
    update: target,
  });

  let contentLength = 0;
  let downloadedBytes = 0;
  const onEvent = (event: DownloadEvent) => {
    if (event.event === "Started") {
      contentLength = event.data.contentLength ?? 0;
    } else if (event.event === "Progress") {
      downloadedBytes += event.data.chunkLength;
      if (contentLength > 0) {
        const progress = Math.min(100, Math.round((downloadedBytes / contentLength) * 100));
        setState({ ...state, progress });
      }
    }
  };

  try {
    await target.downloadAndInstall(onEvent);
    setState({ ...state, status: "downloaded", progress: 100 });
    await relaunch();
  } catch (error) {
    setState({
      status: "error",
      version: target.version,
      progress: 0,
      message: errorMessage(error),
      update: target,
    });
  } finally {
    busy = false;
  }
}

export function dismissUpdateBanner(): void {
  setState({
    ...state,
    bannerDismissed: true,
    dismissedVersion: state.version,
  });
}

export function startUpdaterAutoCheck(): void {
  if (autoStarted || !import.meta.env.PROD || !isTauri()) return;
  autoStarted = true;
  window.setTimeout(() => void checkForUpdates(), 8_000);
  window.setInterval(() => void checkForUpdates(), 4 * 60 * 60 * 1000);
}
