import { useState } from "react";

export interface ConfirmState {
  title: string;
  description: string;
  action: () => void;
}

export function useInputState() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);

  return {
    sidebarOpen,
    setSidebarOpen,
    settingsOpen,
    setSettingsOpen,
    confirmState,
    setConfirmState,
  };
}
