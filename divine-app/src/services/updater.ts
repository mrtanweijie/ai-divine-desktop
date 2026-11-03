import { useSyncExternalStore } from "react";
import { invoke } from "@tauri-apps/api/core";
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

/**
 * 失败发生在哪一段。UI 按它选文案 —— 原来 download/install 失败也报
 * 「检查更新失败」，用户完全看不出是网络问题还是装不上。
 */
export type UpdaterErrorStage = "check" | "download" | "install";

/** 下载+安装的总超时：GitHub 大包（~170MB）慢网络下可能几分钟，但绝不能无限等。 */
const INSTALL_TIMEOUT_MS = 15 * 60 * 1000;

export interface UpdaterState {
  status: UpdaterStatus;
  version: string;
  /**
   * 更新说明原文（来自 `latest.json` 的 `notes`）。
   *
   * **不在 UI 展示**：产品上只告知「发现新版本 vX.Y.Z」，不铺开更新内容。
   * 字段保留是为了排查问题时能拿到原文，别再接到展示层。
   */
  body: string;
  progress: number;
  /** 失败原因（原文，含 Tauri 抛出的底层错误），error / downloaded 两种状态会展示。 */
  message: string;
  errorStage: UpdaterErrorStage | null;
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
  errorStage: null,
  update: null,
  bannerDismissed: false,
  dismissedVersion: "",
};

let state = initialState;
let currentUpdate: Update | null = null;
const listeners = new Set<() => void>();
let autoStarted = false;
let busy = false;

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

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error);
}

/**
 * 记录失败详情，返回同一份文本存进 state。
 *
 * 界面上只展示「检查更新失败，请稍后重试」这类人话（见 UpdaterSection 的错误态）：
 * reqwest 的 `error sending request for url (...)` 对用户毫无意义，还容易让人
 * 以为是自己网络坏了。原文仍写进控制台，排障时能拿到 URL 与错误码。
 */
function reportFailure(stage: string, error: unknown): string {
  const detail = errorMessage(error);
  console.warn(`[updater] ${stage}失败：`, detail, error);
  return detail;
}

/**
 * 给可能永不 settle 的 Promise 加超时。
 *
 * Tauri 的 `downloadAndInstall` 在「下载完、替换 app」阶段卡住时既不 resolve
 * 也不 reject —— 一旦卡住 `busy` 永不释放，「重试」按钮点了没任何反应。
 * 超时至少能把状态放出来，让用户重试或手动装 DMG。
 */
function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(
      () => reject(new Error(`更新超时：${Math.round(ms / 60_000)} 分钟未完成`)),
      ms,
    );
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      },
    );
  });
}

export async function checkForUpdates(): Promise<void> {
  if (!isTauri()) {
    setState({ ...initialState, status: "disabled" });
    return;
  }
  if (busy) {
    // 上一次卡在 error（下载/安装超时）时放行重试，否则按钮点了没反应
    if (state.status !== "error") return;
    busy = false;
  }
  busy = true;
  setState({ ...state, status: "checking", progress: 0, message: "", errorStage: null });
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
        errorStage: null,
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
        errorStage: null,
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
      message: reportFailure("检查更新", error),
      errorStage: "check",
      update: null,
      bannerDismissed: false,
      dismissedVersion: "",
    });
  } finally {
    busy = false;
  }
}

/**
 * 停/起本地后端（sidecar）。
 *
 * 安装更新会把整个 `Divine.app` 换掉，而 sidecar 是 bundle 里的可执行文件
 * （`Contents/MacOS/divine-server`，160MB）。它继续运行会让替换阶段拿到
 * EBUSY/EPERM —— 安装失败时用户只看到一句「检查更新失败」，完全无从判断。
 * 命令不存在（更老的壳）时静默跳过，不能因为停不了后端就不给更新。
 */
async function controlSidecar(action: "stop_sidecar" | "start_sidecar"): Promise<void> {
  try {
    await invoke(action);
  } catch {
    // 老版本没有该命令 / 后端本来就没起 —— 都不阻断更新
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
    errorStage: null,
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
    // 替换 bundle 之前先放掉后端进程，避免安装阶段被占用文件挡住
    await controlSidecar("stop_sidecar");
    await withTimeout(target.downloadAndInstall(onEvent), INSTALL_TIMEOUT_MS);
    setState({ ...state, status: "downloaded", progress: 100, message: "", errorStage: null });
    try {
      await relaunch();
    } catch (error) {
      // 包已经装好了，只是没能自动重启 —— 这不是「更新失败」，
      // 让用户手动退出重开即可（否则会误报失败，还会让人以为是安装坏了）。
      // 重启失败时把后端拉回来，别留一个没有后端的窗口。
      await controlSidecar("start_sidecar");
      setState({
        ...state,
        status: "downloaded",
        progress: 100,
        message: reportFailure("自动重启", error),
      });
    }
  } catch (error) {
    // 安装没成功 → 恢复后端，用户还能继续用当前版本
    await controlSidecar("start_sidecar");
    // 已经收满字节才失败 → 问题在解压/替换 app（安装阶段）；否则是下载本身失败
    const installed =
      (contentLength > 0 && downloadedBytes >= contentLength) || state.progress >= 100;
    setState({
      status: "error",
      version: target.version,
      progress: 0,
      message: reportFailure(installed ? "更新安装" : "更新下载", error),
      errorStage: installed ? "install" : "download",
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
