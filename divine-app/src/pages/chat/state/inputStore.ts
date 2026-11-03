import { useState } from "react";

export interface ConfirmState {
  title: string;
  description: string;
  action: () => void;
}

export function useInputState() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);

  return {
    sidebarOpen,
    setSidebarOpen,
    confirmState,
    setConfirmState,
  };
}
