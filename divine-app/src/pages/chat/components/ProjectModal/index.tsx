import { useEffect, useState } from "react";
import { FolderPlus, Save } from "lucide-react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { isTauri } from "@/services/tauri";
import type { Project } from "@/types";
import {
  PROJECT_ICON_OPTIONS,
  ProjectIcon,
} from "@/pages/chat/components/ProjectIcon";
import "./index.less";

interface ProjectModalProps {
  open: boolean;
  project?: Project | null;
  onClose: () => void;
  onSave: (body: {
    name: string;
    path?: string;
    icon?: string;
  }) => Promise<void> | void;
}

function toFolderName(value: string): string {
  const cleaned = value
    .trim()
    .replace(/[\\/:*?"<>|\u0000-\u001f]+/g, "-")
    .replace(/\s+/g, "-")
    .replace(/\.+$/g, "")
    .slice(0, 80);
  return cleaned || "未命名项目";
}

export function ProjectModal({
  open,
  project,
  onClose,
  onSave,
}: ProjectModalProps) {
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [pathChosen, setPathChosen] = useState(false);
  const [icon, setIcon] = useState("folder");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setName("");
    setPath("");
    setPathChosen(false);
    setIcon(project?.icon ?? "folder");
    setName(project?.name ?? "");
    setPath(project?.path ?? "");
    setPathChosen(Boolean(project));
    setSaving(false);
    setError("");
  }, [open, project]);

  const defaultPath = `~/Documents/Divine/${toFolderName(name)}`;

  const pickFolder = async () => {
    if (!isTauri()) return;
    const selected = await openDialog({ directory: true, multiple: false });
    if (typeof selected !== "string") return;
    setPath(selected);
    const base = selected.replace(/[\\/]+$/, "").split(/[\\/]/).pop();
    setName(base ?? "");
    setPathChosen(true);
  };

  const submit = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("请输入项目名称");
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
      setError(exc instanceof Error ? exc.message : "创建项目失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      title={project ? "编辑项目" : "创建项目"}
      onClose={onClose}
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            取消
          </Button>
          <Button variant="primary" onClick={() => void submit()} loading={saving}>
            <Save size={15} />
            {project ? "保存" : "创建项目"}
          </Button>
        </>
      }
    >
      <div className="project-modal-form">
        <Input
          label="项目名称"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="例如：产品方案"
          autoFocus
        />
        {!project && (
          <div className="source-folder-field">
            <span className="ui-field-label">源文件夹</span>
            <button
              type="button"
              className="project-source-box"
              onClick={() => void pickFolder()}
              disabled={!isTauri()}
            >
              {pathChosen ? (
                <>
                  <FolderPlus size={20} />
                  <span className="project-source-path">{path}</span>
                  <small>点击重新选择</small>
                </>
              ) : (
                <>
                  <FolderPlus size={20} />
                  <span>添加可读取和编辑的文件夹</span>
                </>
              )}
            </button>
            {!pathChosen && (
              <p className="project-default-hint">将创建：{defaultPath}</p>
            )}
          </div>
        )}
        {project && (
          <div className="project-path-readonly">
            <span className="ui-field-label">源文件夹</span>
            <span className="project-path-value">{project.path}</span>
          </div>
        )}
        <div className="project-icon-field">
          <span className="ui-field-label">项目图标</span>
          <div className="project-icon-grid">
            {PROJECT_ICON_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                className={`project-icon-option${
                  icon === option ? " active" : ""
                }`}
                onClick={() => setIcon(option)}
                aria-label={option}
                title={option}
              >
                <ProjectIcon icon={option} size={16} />
              </button>
            ))}
          </div>
        </div>
        {error && <p className="project-modal-error">{error}</p>}
      </div>
    </Modal>
  );
}
