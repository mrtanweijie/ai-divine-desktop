// Renders a unified diff (from edit_files/git_diff results) as a colored,
// collapsible code block. Supports both light and dark themes via CSS vars.
import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

type DiffLineType = "meta" | "hunk" | "add" | "del" | "ctx";

interface DiffLine {
  type: DiffLineType;
  text: string;
}

const MAX_RENDERED_LINES = 600;

export function parseDiffLines(diff: string): DiffLine[] {
  const lines: DiffLine[] = [];
  for (const line of diff.split("\n")) {
    if (
      line.startsWith("diff --git") ||
      line.startsWith("index ") ||
      line.startsWith("--- ") ||
      line.startsWith("+++ ")
    ) {
      lines.push({ type: "meta", text: line });
    } else if (line.startsWith("@@")) {
      lines.push({ type: "hunk", text: line });
    } else if (line.startsWith("+") && !line.startsWith("+++")) {
      lines.push({ type: "add", text: line });
    } else if (line.startsWith("-") && !line.startsWith("---")) {
      lines.push({ type: "del", text: line });
    } else if (line.trim()) {
      lines.push({ type: "ctx", text: line });
    }
  }
  return lines;
}

export function DiffView({ diff, defaultOpen = false }: { diff: string; defaultOpen?: boolean }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen);
  const lines = useMemo(() => parseDiffLines(diff), [diff]);
  const visible = lines.slice(0, MAX_RENDERED_LINES);
  const truncated = lines.length > MAX_RENDERED_LINES;
  const addCount = lines.filter((line) => line.type === "add").length;
  const delCount = lines.filter((line) => line.type === "del").length;

  return (
    <div className="diff-view">
      <div
        role="button"
        tabIndex={0}
        className="diff-view-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setOpen((value) => !value);
          }
        }}
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span>
          {t("tool.diffTitle", "改动 diff")}
          <span className="diff-view-stats">
            <span className="diff-stat-add">+{addCount}</span>
            <span className="diff-stat-del">−{delCount}</span>
          </span>
        </span>
      </div>
      {open && (
        <pre className="diff-view-body">
          {visible.map((line, index) => (
            <div className={`diff-line diff-line-${line.type}`} key={index}>
              {line.text || " "}
            </div>
          ))}
          {truncated && (
            <div className="diff-line diff-line-truncated">
              {t("tool.diffTruncated", "……diff 过长，已截断显示")}
            </div>
          )}
        </pre>
      )}
    </div>
  );
}
