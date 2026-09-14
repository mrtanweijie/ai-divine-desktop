import type { TFunction } from "i18next";
import { Folder, Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { FileTypeIcon } from "@/components/FileTypeIcon";
import type { MentionCandidate, MentionKind, SkillCandidateSource } from "@/types";
import { formatSize } from "@/utils";

import "./index.less";

interface MentionPopupProps {
  kind: MentionKind;
  items: MentionCandidate[];
  activeIndex: number;
  loading: boolean;
  onHover: (index: number) => void;
  onSelect: (item: MentionCandidate) => void;
}

/** 技能类型：知识技能 / 能力技能（executable 与 mcp 同属"能做事"的一类）。 */
type SkillSection = "knowledge" | "executable";

function sectionOf(item: MentionCandidate): SkillSection {
  return item.type === "knowledge" ? "knowledge" : "executable";
}

function kindLabel(section: SkillSection, t: TFunction): string {
  return section === "knowledge"
    ? t("chat.mentionKindKnowledge", "知识")
    : t("chat.mentionKindExecutable", "能力");
}

function sourceLabel(source: SkillCandidateSource, t: TFunction): string {
  if (source === "project") return t("chat.mentionSourceProject", "项目");
  if (source === "user") return t("chat.mentionSourceUser", "用户");
  return t("chat.mentionSourceBuiltin", "内置");
}

/** 文件条目：图标（按后缀）+ 路径 + 体积/目录标记。 */
function FileCandidate({ item }: { item: MentionCandidate }) {
  const { t } = useTranslation();
  return (
    <>
      <span className="mention-icon">
        {item.type === "dir" ? <Folder size={13} /> : <FileTypeIcon name={item.path} size={13} />}
      </span>
      <span className="mention-path" title={item.path}>
        {item.path}
      </span>
      {item.type === "dir" ? (
        <span className="mention-meta">{t("chat.mentionDir", "目录")}</span>
      ) : item.size != null ? (
        <span className="mention-meta">{formatSize(item.size)}</span>
      ) : null}
    </>
  );
}

/** 技能条目：[类型徽标] 技能名 + 描述截断 + 来源徽标。 */
function SkillCandidate({ item }: { item: MentionCandidate }) {
  const { t } = useTranslation();
  const section = sectionOf(item);
  return (
    <>
      <span className={`mention-kind mention-kind--${section}`}>{kindLabel(section, t)}</span>
      <span className="mention-name" title={item.name ?? item.path}>
        {item.path}
      </span>
      {item.description ? (
        <span className="mention-desc" title={item.description}>
          {item.description}
        </span>
      ) : null}
      {item.source ? <span className="mention-source">{sourceLabel(item.source, t)}</span> : null}
    </>
  );
}

/**
 * `@` / `/` 候选浮层。高亮下标与键盘导航由父组件持有，这里只负责展示。
 * 选中用 onMouseDown 而非 onClick：避免 textarea 先失焦、插入位置丢失。
 *
 * 单一标题（`选择技能` / `引用工作区文件`）——技能类型不再用分节标题，改为行内
 * 「知识 / 能力」徽标承载，避免两级标题叠在同一浮层顶部。
 */
export function MentionPopup({
  kind,
  items,
  activeIndex,
  loading,
  onHover,
  onSelect,
}: MentionPopupProps) {
  const { t } = useTranslation();
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const active = listRef.current?.querySelector<HTMLElement>(".mention-item--active");
    active?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, items]);

  if (!loading && items.length === 0) return null;

  return (
    <div className="mention-popup" role="listbox" aria-label={t("chat.mentionTitle", "引用")}>
      <div className="mention-popup-head">
        {kind === "skill"
          ? t("chat.mentionSkillHint", "选择技能")
          : t("chat.mentionFileHint", "引用工作区文件")}
      </div>
      {items.length === 0 ? (
        <div className="mention-empty">
          <Loader2 size={13} className="mention-spin" />
          <span>{t("chat.mentionSearching", "搜索中…")}</span>
        </div>
      ) : (
        <div className="mention-list" ref={listRef}>
          {items.map((item, index) => (
            <div
              key={`${item.kind}:${item.path}`}
              role="option"
              aria-selected={index === activeIndex}
              className={`mention-item${index === activeIndex ? " mention-item--active" : ""}`}
              onMouseEnter={() => onHover(index)}
              onMouseDown={(event) => {
                event.preventDefault();
                onSelect(item);
              }}
            >
              {item.kind === "skill" ? (
                <SkillCandidate item={item} />
              ) : (
                <FileCandidate item={item} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
