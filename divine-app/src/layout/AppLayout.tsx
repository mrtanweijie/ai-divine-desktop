import { Outlet } from "react-router";
import { Toaster } from "@/components/ui/Toast";

export function AppLayout() {
  return (
    <>
      <Outlet />
      <Toaster />
    </>
  );
}
