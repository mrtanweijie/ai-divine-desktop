import { useState } from "react";
import { storageGetRaw, storageRemove, storageSetRaw } from "@/services/storage";
import type { Project, Session } from "@/types";

const LAST_PROJECT_ID_KEY = "divine:last-project-id";
const LAST_SESSION_ID_KEY = "divine:last-session-id";

export interface LastSessionSelection {
  projectId: string | null;
  sessionId: string | null;
}

export function readLastSessionSelection(): LastSessionSelection {
  return {
    projectId: storageGetRaw(LAST_PROJECT_ID_KEY),
    sessionId: storageGetRaw(LAST_SESSION_ID_KEY),
  };
}

export function writeLastSessionSelection(
  projectId: string | null,
  sessionId: string | null,
): void {
  if (projectId) {
    storageSetRaw(LAST_PROJECT_ID_KEY, projectId);
  } else {
    storageRemove(LAST_PROJECT_ID_KEY);
  }
  if (sessionId) {
    storageSetRaw(LAST_SESSION_ID_KEY, sessionId);
  } else {
    storageRemove(LAST_SESSION_ID_KEY);
  }
}

export function useSessionState() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  return {
    sessions,
    setSessions,
    selectedId,
    setSelectedId,
    projects,
    setProjects,
    selectedProjectId,
    setSelectedProjectId,
  };
}
