import { useState } from "react";
import { FolderPlus, Save } from "lucide-react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { useTranslation } from "react-i18next";
import i18next from "@/i18n";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { isTauri } from "@/services/tauri";
import type { Project } from "@/types";
import { PROJECT_ICON_OPTIONS, ProjectIcon } from "@/pages/chat/components/ProjectIcon";
import "./index.less";

interface ProjectModalProps {
  open: boolean;
  project?: Project | null;
  onClose: () => void;
  onSave: (body: { name: string; path?: string; icon?: string }) => Promise<void> | void;
}

function toFolderName(value: string): string {
  const cleaned = value
    .trim()
    // eslint-disable-next-line no-control-regex -- 文件名清洗：剥控制字符是有意行为
    .replace(/[\\/:*?"<>|\u0000-\u001f]+/g, "-")
    .replace(/\s+/g, "-")
    .replace(/\.+$/g, "")
    .slice(0, 80);
  return cleaned || i18next.t("project.unnamed", "未命名项目");
}

export function ProjectModal({ open, project, onClose, onSave }: ProjectModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [pathChosen, setPathChosen] = useState(false);
  const [icon, setIcon] = useState("folder");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // open 变化时重置表单：渲染期调整（React 官方建议，替代 effect 内 setState）
  const [prevOpenKey, setPrevOpenKey] = useState<string | null>(null);
  const openKey = `${open}\u0000${project?.id ?? ""}`;
  if (prevOpenKey !== openKey) {
    setPrevOpenKey(openKey);
    if (open) {
      setName("");
      setPath("");
      setPathChosen(false);
      setIcon(project?.icon ?? "folder");
      setName(project?.name ?? "");
      setPath(project?.path ?? "");
      setPathChosen(Boolean(project));
      setSaving(false);
      setError("");
    }
  }

  const defaultPath = `~/Documents/Divine/${toFolderName(name)}`;

  const pickFolder = async () => {
    if (!isTauri()) return;
    const selected = await openDialog({ directory: true, multiple: false });
    if (typeof selected !== "string") return;
    setPath(selected);
    const base = selected
      .replace(/[\\/]+$/, "")
      .split(/[\\/]/)
      .pop();
    setName(base ?? "");
    setPathChosen(true);
  };

  const submit = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError(t("project.nameRequired", "请输入项目名称"));
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onSave({
        name: trimmedName,
        path: pathChosen ? path : defaultPath,
        icon,
      });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : t("project.createFailed", "创建项目失败"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      title={project ? t("project.edit", "编辑项目") : t("project.create", "创建项目")}
      onClose={onClose}
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel", "取消")}
          </Button>
          <Button variant="primary" onClick={() => void submit()} loading={saving}>
            <Save size={15} />
            {project ? t("common.save", "保存") : t("project.create", "创建项目")}
          </Button>
        </>
      }
    >
      <div className="project-modal-form">
        <Input
          label={t("project.nameLabel", "项目名称")}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("project.namePlaceholder", "例如：产品方案")}
          autoFocus
        />
        {!project && (
          <div className="source-folder-field">
            <span className="ui-field-label">{t("project.sourceFolder", "源文件夹")}</span>
            <div
              role="button"
              tabIndex={isTauri() ? 0 : undefined}
              className="project-source-box"
              onClick={() => void pickFolder()}
              aria-disabled={!isTauri()}
              onKeyDown={(event) => {
                if (!isTauri()) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  void pickFolder();
                }
              }}
            >
              {pathChosen ? (
                <>
                  <FolderPlus size={20} />
                  <span className="project-source-path">{path}</span>
                  <small>{t("project.reselect", "点击重新选择")}</small>
                </>
              ) : (
                <>
                  <FolderPlus size={20} />
                  <span>{t("project.addFolder", "添加可读取和编辑的文件夹")}</span>
                </>
              )}
            </div>
            {!pathChosen && (
              <p className="project-default-hint">
                {t("project.willCreate", "将创建：{{path}}", {
                  path: defaultPath,
                })}
              </p>
            )}
          </div>
        )}
        {project && (
          <div className="project-path-readonly">
            <span className="ui-field-label">{t("project.sourceFolder", "源文件夹")}</span>
            <span className="project-path-value">{project.path}</span>
          </div>
        )}
        <div className="project-icon-field">
          <span className="ui-field-label">{t("project.iconLabel", "项目图标")}</span>
          <div className="project-icon-grid">
            {PROJECT_ICON_OPTIONS.map((option) => (
              <div
                key={option}
                role="radio"
                aria-checked={icon === option}
                tabIndex={0}
                className={`project-icon-option${icon === option ? " active" : ""}`}
                onClick={() => setIcon(option)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setIcon(option);
                  }
                }}
                aria-label={option}
                title={option}
              >
                <ProjectIcon icon={option} size={16} />
              </div>
            ))}
          </div>
        </div>
        {error && <p className="project-modal-error">{error}</p>}
      </div>
    </Modal>
  );
}
