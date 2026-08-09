import { Outlet } from "react-router-dom";
import { Toaster } from "@/components/ui/Toast";

export function AppLayout() {
  return (
    <>
      <Outlet />
      <Toaster />
    </>
  );
}
