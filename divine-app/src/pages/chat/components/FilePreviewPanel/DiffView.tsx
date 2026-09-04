import { FileText, Scissors } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FileDiff } from "@/types";
import { BinaryPreview, isPreviewableBinary } from "./BinaryPreview";

interface DiffViewProps {
  preview: FileDiff;
  relPath: string;
  fileName?: string;
  path?: string;
  changed?: boolean;
}

interface DiffRow {
  type: "hunk" | "meta" | "add" | "del" | "context";
  text: string;
  oldLine: number | null;
  newLine: number | null;
}

/** Rows rendered at most for diff preview; beyond this the diff is cut. */
const MAX_PREVIEW_ROWS = 3000;

function parseDiffRows(diffText: string): DiffRow[] {
  const rows: DiffRow[] = [];
  let oldLine = 0;
  let newLine = 0;
  let inHunk = false;
  for (const raw of diffText.split("\n")) {
    if (rows.length >= MAX_PREVIEW_ROWS) break;
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
  return content
    .split("\n")
    .slice(0, MAX_PREVIEW_ROWS)
    .map((text, index) => ({
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
  path,
  changed = false,
}: DiffViewProps) {
  const { t } = useTranslation();
  const rawDiff = !preview.isBinary ? preview.diffText.trim() : "";
  const diffExceedsLimit =
    rawDiff.split("\n").length > MAX_PREVIEW_ROWS ||
    (!rawDiff && (preview.newContent || preview.oldContent).split("\n").length > MAX_PREVIEW_ROWS);
  const rows =
    !preview.isBinary
      ? rawDiff
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
      {preview.isBinary &&
        (path && isPreviewableBinary(fileName ?? relPath) ? (
          <BinaryPreview path={path} fileName={fileName ?? relPath} />
        ) : (
          <div className="diff-view-state">
            <FileText size={15} />
            <span>{t("file.binaryDiffUnsupported", "二进制文件不支持逐行 diff")}</span>
          </div>
        ))}
      {!preview.isBinary && rows.length === 0 && (
        <div className="diff-view-state">
          <span>{t("file.noVisibleChanges", "当前文件没有可见改动")}</span>
        </div>
      )}
      {!preview.isBinary && diffExceedsLimit && (
        <div className="diff-view-truncated" role="status">
          <Scissors size={12} className="diff-view-truncated-icon" />
          <span>
            {t("file.previewTruncated", "文件过大，仅显示前 {{count}} 行", {
              count: MAX_PREVIEW_ROWS,
            })}
          </span>
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
