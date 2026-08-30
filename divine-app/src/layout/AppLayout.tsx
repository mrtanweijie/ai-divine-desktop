import { Outlet } from "react-router";
import { Toaster } from "@/components/ui/Toast";
import { UpdateBanner } from "@/components/UpdateBanner";
import { startUpdaterAutoCheck } from "@/services/updater";
import { startTaskReminderPolling } from "@/services/scheduledTasks";
import { getSettings } from "@/services/api";
import { isTauri, setGlobalShortcutEnabled } from "@/services/tauri";
import { useEffect } from "react";

export function AppLayout() {
  useEffect(() => {
    startUpdaterAutoCheck();
    const stopPolling = startTaskReminderPolling();
    // 全局快捷键默认由 Rust 侧在启动时注册；用户若已关闭，这里同步注销
    if (isTauri()) {
      void getSettings()
        .then((settings) => {
          if (settings.global_shortcut_enabled === false) {
            return setGlobalShortcutEnabled(false);
          }
        })
        .catch(() => {
          // 设置未就绪时保持默认注册状态
        });
    }
    return stopPolling;
  }, []);

  return (
    <>
      <Outlet />
      <Toaster />
      <UpdateBanner />
    </>
  );
}
