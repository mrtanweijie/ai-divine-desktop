import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { isTauri, isMacosDesktop } from "@/services/tauri";

// macOS 全屏状态同步。
// Rust 端监听 NSWindowWillEnter/ExitFullScreenNotification（动画开始前触发），
// 通过 "window-fullscreen-changed" 事件推到这里，前端立即切换布局 ——
// 按 ESC 退出全屏时红绿灯出现前 actions 就已回到右侧，无遮挡、无延时。
// 非 macOS / 非 Tauri 环境退回 isFullscreen() 轮询兜底。
export function useFullscreen() {
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    let active = true;
    let unlisten: (() => void) | undefined;

    const apply = (value: boolean) => {
      if (active) setFullscreen(value);
    };

    if (isTauri() && isMacosDesktop()) {
      void listen<boolean>("window-fullscreen-changed", (event) => {
        apply(event.payload);
      }).then((fn) => {
        unlisten = fn;
      });
    }

    // 兜底：非 macOS 或事件不可用时用 isFullscreen() 轮询
    let timer: ReturnType<typeof setInterval> | undefined;
    if (!isTauri() || !isMacosDesktop()) {
      const read = async () => {
        let value = false;
        if (isTauri()) {
          try {
            value = await getCurrentWindow().isFullscreen();
          } catch {
            value = false;
          }
        } else {
          value = Boolean(document.fullscreenElement);
        }
        apply(value);
      };
      void read();
      timer = setInterval(() => void read(), 300);
    }

    return () => {
      active = false;
      unlisten?.();
      if (timer) clearInterval(timer);
    };
  }, []);

  return fullscreen;
}
