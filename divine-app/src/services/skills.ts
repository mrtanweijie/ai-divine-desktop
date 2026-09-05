import { request } from "@/services/request";
import type { InstalledSkill } from "@/types";

function skillsQuery(workspace?: string): string {
  return workspace ? `?workspace=${encodeURIComponent(workspace)}` : "";
}

export function listSkills(workspace?: string): Promise<{ skills: InstalledSkill[] }> {
  return request(`/skills${skillsQuery(workspace)}`);
}

export function reloadSkills(
  workspace?: string,
): Promise<{ ok: boolean; skills: InstalledSkill[] }> {
  return request(`/skills/reload${skillsQuery(workspace)}`, {
    method: "POST",
  });
}

export function uninstallSkill(
  name: string,
  workspace?: string,
): Promise<{ ok: boolean; name: string; dir: string }> {
  return request(`/skills/${encodeURIComponent(name)}${skillsQuery(workspace)}`, {
    method: "DELETE",
  });
}
