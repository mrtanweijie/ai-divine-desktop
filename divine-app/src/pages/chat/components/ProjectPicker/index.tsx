import { useEffect, useRef, useState } from "react";
import { ChevronDown, Plus, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/Input";
import type { Project } from "@/types";
import { ProjectIcon } from "@/pages/chat/components/ProjectIcon";
import "./index.less";

interface ProjectPickerProps {
  projects: Project[];
  currentProject: Project | null;
  onSelect: (id: string) => void;
  onNewProject: () => void;
}

export function ProjectPicker({
  projects,
  currentProject,
  onSelect,
  onNewProject,
}: ProjectPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  const filtered = query.trim()
    ? projects.filter((project) => project.name.toLowerCase().includes(query.trim().toLowerCase()))
    : projects;

  useEffect(() => {
    if (!open) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const select = (id: string) => {
    onSelect(id);
    setOpen(false);
    setQuery("");
  };

  return (
    <div className="project-picker" ref={ref}>
      <div
        className="project-picker-trigger"
        role="button"
        tabIndex={0}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            setOpen((value) => !value);
            event.currentTarget.blur();
          }
        }}
      >
        <ProjectIcon icon={currentProject?.icon} size={13} />
        <span className="project-picker-name">
          {currentProject?.name ?? t("chat.chooseProject", "选择项目")}
        </span>
        <ChevronDown size={13} className={open ? "open" : ""} />
      </div>

      {open && (
        <div className="project-picker-panel">
          <div className="project-picker-search">
            <Search size={13} />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("chat.searchProject", "搜索项目")}
              autoFocus
            />
          </div>
          <div className="project-picker-list">
            {filtered.length === 0 ? (
              <div className="project-picker-empty">
                {t("chat.noMatchingProject", "没有匹配的项目")}
              </div>
            ) : (
              filtered.map((project) => (
                <div
                  key={project.id}
                  role="option"
                  aria-selected={false}
                  tabIndex={0}
                  className="project-picker-item"
                  onClick={() => select(project.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      select(project.id);
                    }
                  }}
                >
                  <ProjectIcon icon={project.icon} size={13} />
                  <span>{project.name}</span>
                </div>
              ))
            )}
          </div>
          <div className="project-picker-footer">
            <div
              role="button"
              tabIndex={0}
              className="project-picker-new"
              onClick={() => {
                setOpen(false);
                onNewProject();
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setOpen(false);
                  onNewProject();
                }
              }}
            >
              <Plus size={13} />
              {t("chat.newProject", "新建项目")}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
