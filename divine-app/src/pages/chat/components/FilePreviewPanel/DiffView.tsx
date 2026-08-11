import { Check, FileText, Maximize2, Minimize2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { FileDiff } from "@/types";

interface DiffViewProps {
  preview: FileDiff;
  relPath: string;
  fileName?: string;
  changed?: boolean;
  onAcceptFile?: (relPath: string) => void;
  expanded: boolean;
  onToggleExpand: () => void;
}

interface DiffRow {
  type: "hunk" | "meta" | "add" | "del" | "context";
  text: string;
  oldLine: number | null;
  newLine: number | null;
}

function parseDiffRows(diffText: string): DiffRow[] {
  const rows: DiffRow[] = [];
  let oldLine = 0;
  let newLine = 0;
  let inHunk = false;
  for (const raw of diffText.split("\n")) {
    if (raw.startsWith("@@")) {
      const match = raw.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      oldLine = match ? Number(match[1]) : 0;
      newLine = match ? Number(match[2]) : 0;
      inHunk = true;
      rows.push({ type: "hunk", text: raw, oldLine: null, newLine: null });
      continue;
    }
    if (!inHunk) {
      if (
        raw.startsWith("diff ") ||
        raw.startsWith("index ") ||
        raw.startsWith("--- ") ||
        raw.startsWith("+++ ")
      ) {
        rows.push({ type: "meta", text: raw, oldLine: null, newLine: null });
      }
      continue;
    }
    if (raw.startsWith("+")) {
      rows.push({
        type: "add",
        text: raw.slice(1),
        oldLine: null,
        newLine,
      });
      newLine += 1;
    } else if (raw.startsWith("-")) {
      rows.push({ type: "del", text: raw.slice(1), oldLine, newLine: null });
      oldLine += 1;
    } else {
      rows.push({ type: "context", text: raw, oldLine, newLine });
      oldLine += 1;
      newLine += 1;
    }
  }
  return rows;
}

function fallbackRows(content: string, kind: "add" | "del" | "context"): DiffRow[] {
  return content.split("\n").map((text, index) => ({
    type: kind,
    text,
    oldLine:
      kind === "add"
        ? null
        : kind === "del"
          ? index + 1
          : index + 1,
    newLine:
      kind === "del"
        ? null
        : kind === "add"
          ? index + 1
          : index + 1,
  }));
}

export function DiffView({
  preview,
  relPath,
  fileName,
  changed = false,
  onAcceptFile,
  expanded,
  onToggleExpand,
}: DiffViewProps) {
  const rows =
    !preview.isBinary
      ? preview.diffText.trim()
        ? parseDiffRows(preview.diffText)
        : preview.tracked
          ? fallbackRows(preview.newContent, "context")
          : preview.newContent
            ? preview.isGit || changed
              ? fallbackRows(preview.newContent, "add")
              : fallbackRows(preview.newContent, "context")
            : preview.oldContent
              ? fallbackRows(preview.oldContent, "del")
              : []
      : [];

  return (
    <div className="diff-view">
      <div className="diff-view-head">
        <span className="diff-view-file" title={relPath}>
          {fileName ?? relPath}
        </span>
        {changed && onAcceptFile && (
          <Button
            variant="ghost"
            size="small"
            className="diff-accept-button"
            onClick={() => onAcceptFile(relPath)}
            title="接受变更，清除蓝点"
          >
            <Check size={13} />
            接受
          </Button>
        )}
        <Button
          variant="icon"
          size="small"
          className="diff-expand-button"
          onClick={onToggleExpand}
          title={expanded ? "缩小文件区域" : "扩大文件区域"}
          aria-label={expanded ? "缩小文件区域" : "扩大文件区域"}
        >
          {expanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
        </Button>
      </div>

      {preview.isBinary && (
        <div className="diff-view-state">
          <FileText size={15} />
          <span>二进制文件不支持逐行 diff</span>
        </div>
      )}
      {!preview.isBinary && rows.length === 0 && (
        <div className="diff-view-state">
          <span>当前文件没有可见改动</span>
        </div>
      )}
      {!preview.isBinary && rows.length > 0 && (
        <div className="diff-view-code">
          {rows.map((row, index) => (
            <div
              key={`${row.type}-${row.oldLine ?? ""}-${row.newLine ?? ""}-${index}`}
              className={`diff-line diff-${row.type}`}
            >
              {row.type !== "hunk" && row.type !== "meta" && (
                <>
                  <span className="diff-line-num old">
                    {row.oldLine ?? ""}
                  </span>
                  <span className="diff-line-num new">
                    {row.newLine ?? ""}
                  </span>
                </>
              )}
              <span className="diff-sign">
                {row.type === "add"
                  ? "+"
                  : row.type === "del"
                    ? "-"
                    : ""}
              </span>
              <code>{row.text || "\u00a0"}</code>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
