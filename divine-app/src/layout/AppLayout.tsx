import { Outlet } from "react-router";
import { Toaster } from "@/components/ui/Toast";
import { UpdateBanner } from "@/components/UpdateBanner";
import { startUpdaterAutoCheck } from "@/services/updater";
import { startTaskReminderPolling } from "@/services/scheduledTasks";
import { useEffect } from "react";

export function AppLayout() {
  useEffect(() => {
    startUpdaterAutoCheck();
    const stopPolling = startTaskReminderPolling();
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
