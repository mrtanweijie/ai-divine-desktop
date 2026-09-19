// Detail modal for SKILL.md body, references, dependencies, and metadata.
import { FileText, FolderTree, Package } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Modal } from "@/components/ui/Modal";
import type { InstalledSkill } from "@/types";
import { SkillTypeIcon, skillScriptLabel, sourceLabel, typeLabel } from "../SkillLabels";

interface SkillDetailModalProps {
  skill: InstalledSkill;
  onClose: () => void;
}

export function SkillDetailModal({ skill, onClose }: SkillDetailModalProps) {
  const { t } = useTranslation();
  return (
    <Modal
      open
      title={t("skills.detailTitle", "技能详情")}
      titleSuffix={`v${skill.version}`}
      onClose={onClose}
      width={620}
    >
      <div className="skills-detail">
        <div className="skills-detail-head">
          <div className={`skill-row-icon ${skill.type}`}>
            <SkillTypeIcon skill={skill} />
          </div>
          <div className="skills-detail-title">
            <h3>{skill.name}</h3>
            <div className="skills-detail-meta">
              <span className="skill-badge">{typeLabel(skill.type)}</span>
              <span className="skill-badge muted">{sourceLabel(skill.source) ?? skill.source}</span>
              <span className="skill-badge muted">v{skill.version}</span>
            </div>
          </div>
        </div>

        <p className="skills-detail-description">{skill.description}</p>

        <dl className="skills-detail-grid">
          <div>
            <dt>{t("skills.detailTypeLabel", "类型")}</dt>
            <dd>{typeLabel(skill.type)}</dd>
          </div>
          <div>
            <dt>{t("skills.detailSourceLabel", "来源")}</dt>
            <dd>{sourceLabel(skill.source) ?? skill.source}</dd>
          </div>
          <div>
            <dt>{t("skills.detailScriptLabel", "脚本")}</dt>
            <dd>{skillScriptLabel(skill) || t("common.none", "无")}</dd>
          </div>
          <div>
            <dt>{t("skills.detailPathLabel", "路径")}</dt>
            <dd className="skills-detail-path">{skill.path}</dd>
          </div>
        </dl>

        <section className="skills-detail-section">
          <h4>
            <FileText size={13} />
            {t("skills.bodyTitle", "SKILL.md 正文")}
          </h4>
          <pre className="skills-detail-body">{skill.body || t("skills.noBody", "（无正文）")}</pre>
        </section>

        {skill.references.length > 0 && (
          <section className="skills-detail-section">
            <h4>
              <FolderTree size={13} />
              {t("skills.referencesTitle", "参考资料")}
            </h4>
            <ul className="skills-detail-references">
              {skill.references.map((reference) => (
                <li key={reference}>{reference}</li>
              ))}
            </ul>
          </section>
        )}

        {skill.dependencies.length > 0 && (
          <section className="skills-detail-section">
            <h4>
              <Package size={13} />
              {t("skills.dependenciesTitle", "依赖")}
            </h4>
            <ul className="skills-detail-references">
              {skill.dependencies.map((dependency) => (
                <li key={dependency}>{dependency}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </Modal>
  );
}
