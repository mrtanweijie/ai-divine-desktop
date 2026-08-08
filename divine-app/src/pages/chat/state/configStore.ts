import { useState } from "react";
import type { Settings, WorkspaceCategory } from "@/types";

export function useConfigState() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceCategory[]>([]);
  const [initializing, setInitializing] = useState(true);

  return {
    settings,
    setSettings,
    workspace,
    setWorkspace,
    initializing,
    setInitializing,
  };
}
