// Shared skill labels and type icons used by cards and the detail modal.
import { BookOpen, Braces, Package } from "lucide-react";
import i18next from "@/i18n";
import type { InstalledSkill } from "@/types";

export function sourceLabel(source: string): string {
  if (source === "user") return i18next.t("skills.sourceUser", "用户");
  if (source === "project") return i18next.t("skills.sourceProject", "项目");
  return i18next.t("skills.sourceBuiltin", "内置");
}

export function typeLabel(type: InstalledSkill["type"]): string {
  if (type === "knowledge")
    return i18next.t("skills.typeKnowledge", "知识型");
  if (type === "executable")
    return i18next.t("skills.typeExecutable", "能力型");
  return "MCP";
}

export function SkillTypeIcon({ skill }: { skill: InstalledSkill }) {
  if (skill.type === "executable") return <Braces size={15} />;
  if (skill.type === "mcp") return <Package size={15} />;
  return <BookOpen size={15} />;
}

export function skillScriptLabel(skill: InstalledSkill): string {
  if (!skill.script_path) return "";
  const path = skill.script_path;
  const shortPath = path.startsWith("/")
    ? path.split("/").slice(-3).join("/")
    : path;
  return `${shortPath} · ${skill.script_mode === "json" ? "JSON" : "CLI"}`;
}
