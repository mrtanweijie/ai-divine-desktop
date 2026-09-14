import { request } from "@/services/request";
import { invalidateSessionSkillNames } from "@/services/skillNames";
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
  }).then((data) => {
    // 技能清单已变 → 气泡渲染的技能名集合缓存必须作废，否则新技能要等 TTL 到期才认得出
    invalidateSessionSkillNames();
    return data;
  });
}

export function uninstallSkill(
  name: string,
  workspace?: string,
): Promise<{ ok: boolean; name: string; dir: string }> {
  return request(`/skills/${encodeURIComponent(name)}${skillsQuery(workspace)}`, {
    method: "DELETE",
  }).then((data) => {
    invalidateSessionSkillNames();
    return data;
  });
}
