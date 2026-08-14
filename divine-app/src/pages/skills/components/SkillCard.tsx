// Skill grid card with type badges, script hint, and uninstall action.
import { Braces, ChevronRight, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import type { InstalledSkill } from "@/types";
import {
  SkillTypeIcon,
  skillScriptLabel,
  sourceLabel,
  typeLabel,
} from "../SkillLabels";

interface SkillCardProps {
  skill: InstalledSkill;
  onSelect: (skill: InstalledSkill) => void;
  onUninstall: (skill: InstalledSkill) => void;
}

export function SkillCard({
  skill,
  onSelect,
  onUninstall,
}: SkillCardProps) {
  const { t } = useTranslation();
  return (
    <div
      key={skill.name}
      className={`skill-card ${skill.type}`}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(skill)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          onSelect(skill);
          event.currentTarget.blur();
        }
      }}
    >
      <div className="skill-card-head">
        <div className={`skill-row-icon ${skill.type}`}>
          <SkillTypeIcon skill={skill} />
        </div>
        <div className="skill-card-title-block">
          <div className="skill-row-title">{skill.name}</div>
          <div className="skill-card-badges">
            <span className="skill-badge">{typeLabel(skill.type)}</span>
            <span className="skill-badge muted">
              {sourceLabel(skill.source) ?? skill.source}
            </span>
            <span className="skill-badge muted">v{skill.version}</span>
          </div>
        </div>
      </div>
      <div className="skill-card-desc">{skill.description}</div>
      {skillScriptLabel(skill) && (
        <div className="skill-card-script">
          <Braces size={12} />
          {skillScriptLabel(skill)}
        </div>
      )}
      <div className="skill-card-footer">
        {skill.source !== "builtin" && (
          <Button
            variant="icon"
            size="small"
            className="skill-card-uninstall"
            title={t("skills.uninstall", "卸载 {{name}}", {
              name: skill.name,
            })}
            aria-label={t("skills.uninstall", "卸载 {{name}}", {
              name: skill.name,
            })}
            onClick={(event) => {
              event.stopPropagation();
              onUninstall(skill);
            }}
          >
            <Trash2 size={13} />
          </Button>
        )}
        <span className="skill-card-footer-detail">
          <span>{t("skills.viewDetails", "查看详情")}</span>
          <ChevronRight size={14} />
        </span>
      </div>
    </div>
  );
}
