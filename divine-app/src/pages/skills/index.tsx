import { AlertCircle, PanelLeftOpen, RotateCw, Search, Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { toast } from "@/components/ui/Toast";
import { listSkills, reloadSkills, uninstallSkill } from "@/services/skills";
import type { InstalledSkill } from "@/types";
import { SkillCard } from "./components/SkillCard";
import { SkillDetailModal } from "./components/SkillDetailModal";
import "./index.less";

type SkillFilter = "all" | "knowledge" | "executable";

const MIN_REFRESH_MS = 700;

export function SkillsPage({
  workspacePath,
  onOpenSidebar,
}: {
  workspacePath?: string | null;
  onOpenSidebar: () => void;
}) {
  const { t } = useTranslation();
  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<SkillFilter>("all");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<InstalledSkill | null>(null);
  const [uninstallTarget, setUninstallTarget] = useState<InstalledSkill | null>(null);

  const refresh = useCallback(
    async (reload = false) => {
      setError(null);
      if (reload) {
        const startedAt = performance.now();
        setRefreshing(true);
        try {
          const data = await reloadSkills(workspacePath ?? undefined);
          setSkills(data.skills);
          toast.success(t("skills.refreshed", "技能列表已刷新"));
        } catch (refreshError) {
          setError(
            refreshError instanceof Error
              ? refreshError.message
              : t("skills.loadFailed", "技能列表加载失败"),
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
            : t("skills.loadFailed", "技能列表加载失败"),
        );
      } finally {
        setLoading(false);
      }
    },
    [t, workspacePath],
  );

  const handleUninstall = useCallback(
    async (skill: InstalledSkill) => {
      setUninstallTarget(null);
      try {
        const data = await uninstallSkill(skill.name, workspacePath ?? undefined);
        setSkills((prev) => prev.filter((item) => item.name !== data.name));
        toast.success(
          t("skills.uninstalled", "技能“{{name}}”已卸载", {
            name: skill.name,
          }),
        );
      } catch (uninstallError) {
        toast.error(
          uninstallError instanceof Error
            ? uninstallError.message
            : t("skills.uninstallFailed", "卸载失败"),
        );
      }
    },
    [t, workspacePath],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 挂载取数：refresh 为 async，setState 在 await 之后
    void refresh();
  }, [refresh]);

  const counts = useMemo(() => {
    const knowledge = skills.filter((skill) => skill.type === "knowledge").length;
    const executable = skills.filter((skill) => skill.type === "executable").length;
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
        <Flex align="center" gap={8} className="skills-header-actions">
          <Button
            variant="icon"
            className="scheduled-sidebar-button"
            onClick={onOpenSidebar}
            aria-label={t("common.expandSessionList", "展开会话列表")}
            title={t("session.list", "会话列表")}
          >
            <PanelLeftOpen size={15} />
          </Button>
          <div className="skills-search">
            <Search size={14} />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("skills.search", "搜索技能")}
              aria-label={t("skills.search", "搜索技能")}
            />
          </div>
          <Button
            variant="secondary"
            size="small"
            className="skills-refresh-button"
            disabled={refreshing}
            onClick={() => void refresh(true)}
            aria-busy={refreshing}
          >
            <RotateCw size={14} className={refreshing ? "skills-refresh-spinning" : undefined} />
            {t("skills.refresh", "刷新")}
          </Button>
        </Flex>
      </header>

      <div className="skills-install-tip">
        <div className="skills-install-tip-title">
          <Sparkles size={14} />
          <span>{t("skills.installTitle", "安装方法")}</span>
        </div>
        <div className="skills-install-tip-body">
          <Trans i18nKey="skills.installTip">
            将包含 <code>SKILL.md</code> 的目录放入项目 <code>.divine/skills/</code> 或用户{" "}
            <code>~/.divine/skills/</code>
            ；也可以直接在对话中给 Agent 一个 GitHub 仓库地址，由 Agent 预览并安装。
          </Trans>
        </div>
      </div>

      {error && (
        <div className="skills-notice">
          <AlertCircle size={15} />
          <span>{error}</span>
          <Button size="small" variant="ghost" onClick={() => setError(null)}>
            {t("common.close", "关闭")}
          </Button>
        </div>
      )}

      <div className="skills-toolbar">
        <div className="skills-summary">
          <span>
            {t("skills.totalCount", "共 {{count}} 个技能", {
              count: counts.total,
            })}
          </span>
          <span className="skills-summary-sep">·</span>
          <span>
            {t("skills.knowledgeCount", "知识型 {{count}}", {
              count: counts.knowledge,
            })}
          </span>
          <span className="skills-summary-sep">·</span>
          <span>
            {t("skills.executableCount", "能力型 {{count}}", {
              count: counts.executable,
            })}
          </span>
        </div>
        <div
          className="skills-filter"
          role="group"
          aria-label={t("skills.filterLabel", "技能类型筛选")}
        >
          {(
            [
              ["all", t("skills.filterAll", "全部")],
              ["knowledge", t("skills.filterKnowledge", "知识型")],
              ["executable", t("skills.filterExecutable", "能力型")],
            ] as const
          ).map(([value, label]) => (
            <div
              key={value}
              role="tab"
              aria-selected={filter === value}
              tabIndex={0}
              className={`skills-filter-item${filter === value ? " active" : ""}`}
              onClick={() => setFilter(value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setFilter(value);
                }
              }}
            >
              {label}
            </div>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="skills-empty">{t("common.loading", "加载中...")}</div>
      ) : (
        <div className="skills-content">
          {filteredSkills.length > 0 ? (
            <div className="skill-grid">
              {filteredSkills.map((skill) => (
                <SkillCard
                  key={skill.name}
                  skill={skill}
                  onSelect={setSelected}
                  onUninstall={setUninstallTarget}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<Sparkles size={18} />}
              title={
                search || filter !== "all"
                  ? t("skills.noMatches", "没有匹配的技能")
                  : t("skills.noneInstalled", "还没有安装技能")
              }
              description={
                search || filter !== "all"
                  ? t("skills.noMatchesHint", "换个关键词或筛选条件试试")
                  : t(
                      "skills.noneInstalledHint",
                      "安装后的技能会出现在这里，也可以在对话中让 Agent 安装",
                    )
              }
            />
          )}
        </div>
      )}

      {selected && <SkillDetailModal skill={selected} onClose={() => setSelected(null)} />}
      {uninstallTarget && (
        <ConfirmDialog
          title={t("skills.uninstallTitle", "卸载技能")}
          description={t(
            "skills.uninstallConfirm",
            "确定卸载技能“{{name}}”吗？会删除它的技能目录，无法撤销。",
            { name: uninstallTarget.name },
          )}
          onConfirm={() => void handleUninstall(uninstallTarget)}
          onCancel={() => setUninstallTarget(null)}
        />
      )}
    </div>
  );
}
