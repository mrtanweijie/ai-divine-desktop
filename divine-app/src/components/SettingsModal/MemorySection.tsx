import { useCallback, useEffect, useState } from "react";
import { Brain, Check, ChevronDown, RefreshCw, Sparkles, Trash2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MemoryItem } from "@/services/memories";
import {
  confirmMemory,
  deleteMemory,
  importMemory,
  listMemories,
  rejectMemory,
} from "@/services/memories";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Select } from "@/components/ui/Select";
import { TextArea } from "@/components/ui/TextArea";
import "./MemorySection.less";

const CATEGORY_KEYS: Record<string, string> = {
  preference: "settings.memory.catPreference",
  fact: "settings.memory.catFact",
  event: "settings.memory.catEvent",
  procedure: "settings.memory.catProcedure",
};

const IMPORT_CATEGORIES = [
  { value: "procedure", labelKey: "settings.memory.catProcedure" },
  { value: "preference", labelKey: "settings.memory.catPreference" },
  { value: "fact", labelKey: "settings.memory.catFact" },
  { value: "event", labelKey: "settings.memory.catEvent" },
];

function formatTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

interface MemorySectionProps {
  onConfirm?: (title: string, description: string, action: () => void) => void;
}

export function MemorySection({ onConfirm }: MemorySectionProps) {
  const { t } = useTranslation();
  const [active, setActive] = useState<MemoryItem[]>([]);
  const [pending, setPending] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  // 待确认面板开合：null = 跟随自动策略（有待确认项就展开），用户点击后固定
  const [pendingManualOpen, setPendingManualOpen] = useState<boolean | null>(null);
  const pendingOpen = pendingManualOpen ?? pending.length > 0;
  const [activeOpen, setActiveOpen] = useState(true);
  const [importContent, setImportContent] = useState("");
  const [importCategory, setImportCategory] = useState("procedure");
  const [importing, setImporting] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [activeResult, pendingResult] = await Promise.all([
        listMemories("active"),
        listMemories("pending"),
      ]);
      setActive(activeResult.memories);
      setPending(pendingResult.memories);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 首次挂载拉取列表（reload 内含 loading 态），与 McpSection 同模式
    void reload();
  }, [reload]);

  const runAction = useCallback(
    (action: () => Promise<unknown>) => {
      void action()
        .then(() => reload())
        .catch((cause) => {
          setError(cause instanceof Error ? cause.message : String(cause));
        });
    },
    [reload],
  );

  const handleDelete = (item: MemoryItem) => {
    const action = () => deleteMemory(item.id);
    if (onConfirm) {
      onConfirm(t("settings.memory.deleteTitle", "删除这条记忆？"), item.content, action);
    } else {
      runAction(action);
    }
  };

  const handleImport = () => {
    const content = importContent.trim();
    if (!content || importing) return;
    setImporting(true);
    void importMemory({ content, category: importCategory })
      .then(() => {
        setImportContent("");
        return reload();
      })
      .catch((cause) => {
        setError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => setImporting(false));
  };

  /** 统一的折叠面板：实线容器 + 可点击头部（状态点/标题/计数/说明/chevron） */
  const renderPanel = (options: {
    dotClass: string;
    title: string;
    sub: string;
    count: number;
    open: boolean;
    onToggle: () => void;
    body: React.ReactNode;
  }) => (
    <div className="settings-memory-panel">
      <button
        type="button"
        className="settings-memory-toggle"
        aria-expanded={options.open}
        onClick={options.onToggle}
      >
        <span className={`settings-memory-group-dot ${options.dotClass}`} aria-hidden />
        <span className="settings-memory-toggle-title">{options.title}</span>
        {options.count > 0 ? <span className="settings-memory-count">{options.count}</span> : null}
        <span className="settings-memory-toggle-sub">{options.sub}</span>
        <ChevronDown
          size={14}
          className={`settings-memory-chevron${options.open ? " open" : ""}`}
        />
      </button>
      {options.open ? <div className="settings-memory-panel-body">{options.body}</div> : null}
    </div>
  );

  const renderRow = (item: MemoryItem, pendingFlag: boolean) => (
    <div
      key={item.id}
      className={`settings-memory-row${pendingFlag ? " settings-memory-row--pending" : ""}`}
    >
      <div className="settings-memory-row-top">
        <span className={`settings-memory-badge settings-memory-badge--${item.category}`}>
          {t(CATEGORY_KEYS[item.category] ?? "settings.memory.catFact", item.category)}
        </span>
        {item.project_id ? (
          <span className="settings-memory-badge settings-memory-badge--project">
            {t("settings.memory.scopeProject", "项目")}
          </span>
        ) : null}
        <span
          className={`settings-memory-row-meta${pendingFlag ? "" : " settings-memory-row-meta--stack"}`}
        >
          <span className="settings-memory-time">{formatTime(item.updated_at)}</span>
          {pendingFlag ? (
            <>
              <Button
                size="small"
                variant="primary"
                onClick={() => runAction(() => confirmMemory(item.id))}
              >
                <Check size={12} />
                {t("settings.memory.confirm", "确认记住")}
              </Button>
              <Button
                size="small"
                variant="ghost"
                onClick={() => runAction(() => rejectMemory(item.id))}
              >
                <X size={12} />
                {t("settings.memory.reject", "丢弃")}
              </Button>
            </>
          ) : (
            <Button
              size="small"
              variant="icon"
              className="settings-memory-delete"
              onClick={() => handleDelete(item)}
              aria-label={t("settings.memory.delete", "删除")}
              title={t("settings.memory.delete", "删除")}
            >
              <Trash2 size={11} />
            </Button>
          )}
        </span>
      </div>
      <div className="settings-memory-content">{item.content}</div>
    </div>
  );

  return (
    <div className="settings-form settings-memory">
      <div className="settings-memory-header">
        <p className="settings-memory-hint">
          {t(
            "settings.memory.hint",
            "AI 跨会话记住的用户信息。与已有记忆矛盾的新记忆会先挂起，经你确认后生效。",
          )}
        </p>
        <Button
          variant="icon"
          size="small"
          onClick={() => void reload()}
          aria-label={t("common.refresh", "刷新")}
          title={t("common.refresh", "刷新")}
        >
          <RefreshCw size={14} className={loading ? "settings-memory-spin" : undefined} />
        </Button>
      </div>

      {error ? <p className="settings-memory-error">{error}</p> : null}

      <section className="settings-memory-group">
        {renderPanel({
          dotClass: "settings-memory-group-dot--import",
          title: t("settings.memory.importTitle", "手动导入"),
          sub: t("settings.memory.importHint", "把稳定的做事方法 / runbook 存为程序记忆"),
          count: 0,
          open: importOpen,
          onToggle: () => setImportOpen((value) => !value),
          body: (
            <>
              <TextArea
                value={importContent}
                onChange={(event) => setImportContent(event.target.value)}
                placeholder={t(
                  "settings.memory.importPlaceholder",
                  "例如：构建命令：pnpm build；测试前先跑迁移脚本",
                )}
                rows={3}
              />
              <div className="settings-memory-import-row">
                <Select
                  value={importCategory}
                  onChange={setImportCategory}
                  options={IMPORT_CATEGORIES.map((entry) => ({
                    value: entry.value,
                    label: t(entry.labelKey, entry.value),
                  }))}
                />
                <Button
                  variant="primary"
                  size="small"
                  onClick={handleImport}
                  disabled={importing || !importContent.trim()}
                >
                  <Sparkles size={13} />
                  {t("settings.memory.importAction", "导入")}
                </Button>
              </div>
            </>
          ),
        })}
      </section>

      <section className="settings-memory-group">
        {renderPanel({
          dotClass: "settings-memory-group-dot--pending",
          title: t("settings.memory.pendingTitle", "待确认"),
          sub: t("settings.memory.pendingSub", "与已有记忆矛盾的新记忆会挂起在这里，确认后生效"),
          count: pending.length,
          open: pendingOpen,
          onToggle: () => setPendingManualOpen(!pendingOpen),
          body:
            pending.length === 0 ? (
              <p className="settings-memory-empty-line">
                {t("settings.memory.pendingEmpty", "没有待确认的记忆")}
              </p>
            ) : (
              pending.map((item) => renderRow(item, true))
            ),
        })}
      </section>

      <section className="settings-memory-group">
        {renderPanel({
          dotClass: "settings-memory-group-dot--active",
          title: t("settings.memory.activeTitle", "已记住"),
          sub: t("settings.memory.activeSub", "AI 正在使用的长期记忆，可随时删除或纠正"),
          count: active.length,
          open: activeOpen,
          onToggle: () => setActiveOpen((value) => !value),
          body:
            active.length === 0 ? (
              <EmptyState
                icon={<Brain size={26} />}
                title={t("settings.memory.activeEmpty", "还没有长期记忆")}
                description={t(
                  "settings.memory.activeEmptyHint",
                  "对话中让 AI「记住」的信息会出现在这里，可随时删除或纠正",
                )}
              />
            ) : (
              active.map((item) => renderRow(item, false))
            ),
        })}
      </section>
    </div>
  );
}
