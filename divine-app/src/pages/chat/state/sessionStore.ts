import { useState } from "react";
import type { Project, Session } from "@/types";

const LAST_PROJECT_ID_KEY = "divine:last-project-id";
const LAST_SESSION_ID_KEY = "divine:last-session-id";

export interface LastSessionSelection {
  projectId: string | null;
  sessionId: string | null;
}

export function readLastSessionSelection(): LastSessionSelection {
  try {
    return {
      projectId: localStorage.getItem(LAST_PROJECT_ID_KEY),
      sessionId: localStorage.getItem(LAST_SESSION_ID_KEY),
    };
  } catch {
    return { projectId: null, sessionId: null };
  }
}

export function writeLastSessionSelection(
  projectId: string | null,
  sessionId: string | null
): void {
  try {
    if (projectId) {
      localStorage.setItem(LAST_PROJECT_ID_KEY, projectId);
    } else {
      localStorage.removeItem(LAST_PROJECT_ID_KEY);
    }
    if (sessionId) {
      localStorage.setItem(LAST_SESSION_ID_KEY, sessionId);
    } else {
      localStorage.removeItem(LAST_SESSION_ID_KEY);
    }
  } catch {
    // localStorage unavailable, selection stays in memory
  }
}

export function useSessionState() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    null
  );

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
