import { useState } from "react";
import type { Settings, WorkspaceCategory } from "@/types";

export function useConfigState() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceCategory[]>([]);

  return {
    settings,
    setSettings,
    workspace,
    setWorkspace,
  };
}
