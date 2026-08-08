import { useState } from "react";
import type { Session } from "@/types";

export function useSessionState() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return { sessions, setSessions, selectedId, setSelectedId };
}
