import { Outlet } from "react-router";
import { Toaster } from "@/components/ui/Toast";
import { UpdateBanner } from "@/components/UpdateBanner";
import { startUpdaterAutoCheck } from "@/services/updater";
import { useEffect } from "react";

export function AppLayout() {
  useEffect(() => {
    startUpdaterAutoCheck();
  }, []);

  return (
    <>
      <Outlet />
      <Toaster />
      <UpdateBanner />
    </>
  );
}
