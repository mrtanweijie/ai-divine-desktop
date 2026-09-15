import { request } from "@/services/request";
import { invalidateSessionSkillNames } from "@/services/skillNames";
import type { InstalledSkill } from "@/types";

/** `request<T>` 的返回类型必须显式给出，否则 T 推导为 unknown，与函数声明的返回类型不符 */
type SkillsReloadResult = { ok: boolean; skills: InstalledSkill[] };
type SkillUninstallResult = { ok: boolean; name: string; dir: string };

function skillsQuery(workspace?: string): string {
  return workspace ? `?workspace=${encodeURIComponent(workspace)}` : "";
}

export function listSkills(workspace?: string): Promise<{ skills: InstalledSkill[] }> {
  return request(`/skills${skillsQuery(workspace)}`);
}

export function reloadSkills(workspace?: string): Promise<SkillsReloadResult> {
  return request<SkillsReloadResult>(`/skills/reload${skillsQuery(workspace)}`, {
    method: "POST",
  }).then((data) => {
    // 技能清单已变 → 气泡渲染的技能名集合缓存必须作废，否则新技能要等 TTL 到期才认得出
    invalidateSessionSkillNames();
    return data;
  });
}

export function uninstallSkill(name: string, workspace?: string): Promise<SkillUninstallResult> {
  return request<SkillUninstallResult>(
    `/skills/${encodeURIComponent(name)}${skillsQuery(workspace)}`,
    {
      method: "DELETE",
    },
  ).then((data) => {
    invalidateSessionSkillNames();
    return data;
  });
}
