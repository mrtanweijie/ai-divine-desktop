import {
  AlertCircle,
  BookOpen,
  Braces,
  ChevronRight,
  FileText,
  FolderTree,
  Package,
  RotateCw,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { toast } from "@/components/ui/Toast";
import {
  listSkills,
  reloadSkills,
  uninstallSkill,
} from "@/services/skills";
import type { InstalledSkill } from "@/types";
import "./index.less";

type SkillFilter = "all" | "knowledge" | "executable";

const MIN_REFRESH_MS = 700;

const SOURCE_LABELS: Record<string, string> = {
  user: "用户",
  project: "项目",
  builtin: "内置",
};

const TYPE_LABELS: Record<InstalledSkill["type"], string> = {
  knowledge: "知识型",
  executable: "能力型",
  mcp: "MCP",
};

function SkillTypeIcon({ skill }: { skill: InstalledSkill }) {
  if (skill.type === "executable") return <Braces size={15} />;
  if (skill.type === "mcp") return <Package size={15} />;
  return <BookOpen size={15} />;
}

function skillScriptLabel(skill: InstalledSkill): string {
  if (!skill.script_path) return "";
  const path = skill.script_path;
  const shortPath = path.startsWith("/")
    ? path.split("/").slice(-3).join("/")
    : path;
  return `${shortPath} · ${skill.script_mode === "json" ? "JSON" : "CLI"}`;
}

export function SkillsPage({
  workspacePath,
}: {
  workspacePath?: string | null;
}) {
  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<SkillFilter>("all");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<InstalledSkill | null>(null);
  const [uninstallTarget, setUninstallTarget] =
    useState<InstalledSkill | null>(null);

  const refresh = useCallback(
    async (reload = false) => {
      setError(null);
      if (reload) {
        const startedAt = performance.now();
        setRefreshing(true);
        try {
          const data = await reloadSkills(workspacePath ?? undefined);
          setSkills(data.skills);
          toast.success("技能列表已刷新");
        } catch (refreshError) {
          setError(
            refreshError instanceof Error
              ? refreshError.message
              : "技能列表加载失败"
          );
        } finally {
          const remaining = MIN_REFRESH_MS - (performance.now() - startedAt);
          if (remaining > 0) {
            await new Promise((resolve) => setTimeout(resolve, remaining));
          }
          setRefreshing(false);
        }
        return;
      }

      setLoading(true);
      try {
        const data = await listSkills(workspacePath ?? undefined);
        setSkills(data.skills);
      } catch (refreshError) {
        setError(
          refreshError instanceof Error
            ? refreshError.message
            : "技能列表加载失败"
        );
      } finally {
        setLoading(false);
      }
    },
    [workspacePath]
  );

  const handleUninstall = useCallback(
    async (skill: InstalledSkill) => {
      setUninstallTarget(null);
      try {
        const data = await uninstallSkill(
          skill.name,
          workspacePath ?? undefined
        );
        setSkills((prev) =>
          prev.filter((item) => item.name !== data.name)
        );
        toast.success(`技能“${skill.name}”已卸载`);
      } catch (uninstallError) {
        toast.error(
          uninstallError instanceof Error
            ? uninstallError.message
            : "卸载失败"
        );
      }
    },
    [workspacePath]
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const counts = useMemo(() => {
    const knowledge = skills.filter(
      (skill) => skill.type === "knowledge"
    ).length;
    const executable = skills.filter(
      (skill) => skill.type === "executable"
    ).length;
    return { total: skills.length, knowledge, executable };
  }, [skills]);

  const filteredSkills = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return skills.filter((skill) => {
      if (filter === "executable" && skill.type !== "executable") {
        return false;
      }
      if (filter === "knowledge" && skill.type !== "knowledge") {
        return false;
      }
      if (!keyword) return true;
      return (
        skill.name.toLowerCase().includes(keyword) ||
        skill.description.toLowerCase().includes(keyword) ||
        skill.body.toLowerCase().includes(keyword)
      );
    });
  }, [filter, search, skills]);

  return (
    <div className="skills-page">
      <header className="skills-header">
        <div className="skills-search">
          <Search size={14} />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索技能"
            aria-label="搜索技能"
          />
        </div>
        <Flex align="center" gap={8} className="skills-header-actions">
          <Button
            variant="secondary"
            size="small"
            className="skills-refresh-button"
            disabled={refreshing}
            onClick={() => void refresh(true)}
            aria-busy={refreshing}
          >
            <RotateCw
              size={14}
              className={refreshing ? "skills-refresh-spinning" : undefined}
            />
            刷新
          </Button>
        </Flex>
      </header>

      {error && (
        <div className="skills-notice">
          <AlertCircle size={15} />
          <span>{error}</span>
          <Button size="small" variant="ghost" onClick={() => setError(null)}>
            关闭
          </Button>
        </div>
      )}

      <div className="skills-toolbar">
        <div className="skills-summary">
          <span>共 {counts.total} 个技能</span>
          <span className="skills-summary-sep">·</span>
          <span>知识型 {counts.knowledge}</span>
          <span className="skills-summary-sep">·</span>
          <span>能力型 {counts.executable}</span>
        </div>
        <div className="skills-filter" role="group" aria-label="技能类型筛选">
          {(
            [
              ["all", "全部"],
              ["knowledge", "知识型"],
              ["executable", "能力型"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={`skills-filter-item${
                filter === value ? " active" : ""
              }`}
              onClick={() => setFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="skills-empty">加载中...</div>
      ) : (
        <div className="skills-content">
          {filteredSkills.length > 0 ? (
            <div className="skill-grid">
              {filteredSkills.map((skill) => (
                <div
                  key={skill.name}
                  className={`skill-card ${skill.type}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelected(skill)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      setSelected(skill);
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
                        <span className="skill-badge">
                          {TYPE_LABELS[skill.type]}
                        </span>
                        <span className="skill-badge muted">
                          {SOURCE_LABELS[skill.source] ?? skill.source}
                        </span>
                        <span className="skill-badge muted">
                          v{skill.version}
                        </span>
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
                        title={`卸载 ${skill.name}`}
                        aria-label={`卸载 ${skill.name}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          setUninstallTarget(skill);
                        }}
                      >
                        <Trash2 size={13} />
                      </Button>
                    )}
                    <span className="skill-card-footer-detail">
                      <span>查看详情</span>
                      <ChevronRight size={14} />
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<Sparkles size={18} />}
              title={search || filter !== "all" ? "没有匹配的技能" : "还没有安装技能"}
              description={
                search || filter !== "all"
                  ? "换个关键词或筛选条件试试"
                  : "安装后的技能会出现在这里，也可以在对话中让 Agent 安装"
              }
            />
          )}
        </div>
      )}

      {selected && (
        <SkillDetailModal
          skill={selected}
          onClose={() => setSelected(null)}
        />
      )}
      {uninstallTarget && (
        <ConfirmDialog
          title="卸载技能"
          description={`确定卸载技能“${uninstallTarget.name}”吗？会删除它的技能目录，无法撤销。`}
          onConfirm={() => void handleUninstall(uninstallTarget)}
          onCancel={() => setUninstallTarget(null)}
        />
      )}
    </div>
  );
}

function SkillDetailModal({
  skill,
  onClose,
}: {
  skill: InstalledSkill;
  onClose: () => void;
}) {
  return (
    <Modal
      open
      title="技能详情"
      titleSuffix={`v${skill.version}`}
      headerAction={
        <Button
          variant="icon"
          size="small"
          onClick={onClose}
          title="关闭"
          aria-label="关闭"
        >
          <X size={15} />
        </Button>
      }
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
              <span className="skill-badge">{TYPE_LABELS[skill.type]}</span>
              <span className="skill-badge muted">
                {SOURCE_LABELS[skill.source] ?? skill.source}
              </span>
              <span className="skill-badge muted">v{skill.version}</span>
            </div>
          </div>
        </div>

        <p className="skills-detail-description">{skill.description}</p>

        <dl className="skills-detail-grid">
          <div>
            <dt>类型</dt>
            <dd>{TYPE_LABELS[skill.type]}</dd>
          </div>
          <div>
            <dt>来源</dt>
            <dd>{SOURCE_LABELS[skill.source] ?? skill.source}</dd>
          </div>
          <div>
            <dt>脚本</dt>
            <dd>{skillScriptLabel(skill) || "无"}</dd>
          </div>
          <div>
            <dt>路径</dt>
            <dd className="skills-detail-path">{skill.path}</dd>
          </div>
        </dl>

        <section className="skills-detail-section">
          <h4>
            <FileText size={13} />
            SKILL.md 正文
          </h4>
          <pre className="skills-detail-body">
            {skill.body || "（无正文）"}
          </pre>
        </section>

        {skill.references.length > 0 && (
          <section className="skills-detail-section">
            <h4>
              <FolderTree size={13} />
              参考资料
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
              依赖
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
