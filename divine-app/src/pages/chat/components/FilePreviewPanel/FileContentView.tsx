import {
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from "react";
import { FileText, Maximize2, Minimize2, Scissors } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ThemedToken } from "shiki";
import { Button } from "@/components/ui/Button";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import type { FileDiff } from "@/types";
import { useTheme } from "@/services/theme";
import { normalizeLanguage } from "@/pages/chat/components/MarkdownView/language";
import { WebPreviewBlock } from "@/pages/chat/components/MarkdownView/WebPreviewBlock";

interface FileContentViewProps {
  preview: FileDiff;
  relPath: string;
  fileName?: string;
  expanded: boolean;
  onToggleExpand: () => void;
}

/** Rows rendered at most for preview; beyond this the content is cut with a notice. */
const MAX_PREVIEW_ROWS = 3000;

function truncateLines(content: string, maxRows: number): { text: string; truncated: boolean } {
  if (maxRows <= 0) return { text: "", truncated: false };
  const lines = content.split("\n");
  if (lines.length <= maxRows) return { text: content, truncated: false };
  return { text: lines.slice(0, maxRows).join("\n"), truncated: true };
}

function languageFromPath(filePath: string): string | undefined {
  const name = filePath.split("/").pop() ?? filePath;
  if (name === "Dockerfile") return "dockerfile";
  if (name === "Makefile") return "makefile";
  return name.split(".").pop() || undefined;
}

function webPreviewLanguage(filePath: string): "html" | "svg" | null {
  const name = filePath.split("/").pop() ?? filePath;
  const ext = name.toLowerCase().split(".").pop() || "";
  if (ext === "html" || ext === "htm") return "html";
  if (ext === "svg") return "svg";
  return null;
}

function tokenStyle(token: ThemedToken): CSSProperties {
  const style: CSSProperties = {};
  if (token.color) style.color = token.color;
  const font = token.fontStyle;
  if (font) {
    if (font & 1) style.fontStyle = "italic";
    if (font & 2) style.fontWeight = "bold";
    if (font & 4) style.textDecoration = "underline";
  }
  return style;
}

function CodePreview({ code, relPath }: { code: string; relPath: string }) {
  const { t } = useTranslation();
  const preview = useMemo(() => truncateLines(code || "", MAX_PREVIEW_ROWS), [code]);
  const content = preview.text;
  const theme = useTheme();
  const language = useMemo(
    () => normalizeLanguage(languageFromPath(relPath)),
    [relPath]
  );
  const [lines, setLines] = useState<ThemedToken[][] | null>(null);

  useEffect(() => {
    let active = true;
    setLines(null);
    void import("@/pages/chat/components/MarkdownView/shiki")
      .then(({ getHighlighter, highlightTheme }) => {
        return getHighlighter().then((highlighter) => ({
          highlighter,
          highlightTheme,
        }));
      })
      .then((highlighter) => {
        if (!active) return;
        try {
          const result = highlighter.highlighter.codeToTokens(content, {
            lang: language,
            theme: highlighter.highlightTheme(theme),
          });
          if (active) setLines(result.tokens);
        } catch {
          if (active) setLines([]);
        }
      })
      .catch(() => {
        if (active) setLines([]);
      });
    return () => {
      active = false;
    };
  }, [content, language, theme]);

  if (!content) {
    return (
      <div className="diff-view-state">
        <span>{t("file.emptyContent", "文件内容为空")}</span>
      </div>
    );
  }

  if (lines === null) {
    return (
      <div className="diff-view-state">
        <LoadingOrb state="searching" size={20} speed={2} />
        <span>{t("file.loadingCode", "加载代码...")}</span>
      </div>
    );
  }

  const rendered =
    lines.length > 0
      ? lines
      : content.split("\n").map((line) => [{ content: line } as ThemedToken]);

  return (
    <div className="diff-view-code code-preview">
      {preview.truncated && (
        <div className="diff-view-truncated" role="status">
          <Scissors size={12} className="diff-view-truncated-icon" />
          <span>
            {t("file.previewTruncated", "文件过大，仅显示前 {{count}} 行", {
              count: MAX_PREVIEW_ROWS,
            })}
          </span>
        </div>
      )}
      {rendered.map((line, index) => (
        <div key={index} className="file-content-line">
          <span className="file-content-line-num">{index + 1}</span>
          <code>
            {line.length > 0
              ? line.map((token, tokenIndex) => (
                  <span key={tokenIndex} style={tokenStyle(token)}>
                    {token.content}
                  </span>
                ))
              : "\u00a0"}
          </code>
        </div>
      ))}
    </div>
  );
}

export function FileContentView({
  preview,
  relPath,
  fileName,
  expanded,
  onToggleExpand,
}: FileContentViewProps) {
  const { t } = useTranslation();
  const content = preview.newContent || preview.oldContent || "";
  const webLanguage = webPreviewLanguage(relPath);
  return (
    <div className="diff-view file-content-view">
      <div className="diff-view-head">
        <span className="diff-view-file" title={relPath}>
          {fileName ?? relPath}
        </span>
        <Button
          variant="icon"
          size="small"
          className="diff-expand-button"
          onClick={onToggleExpand}
          title={
            expanded
              ? t("file.shrinkArea", "缩小文件区域")
              : t("file.expandArea", "扩大文件区域")
          }
          aria-label={
            expanded
              ? t("file.shrinkArea", "缩小文件区域")
              : t("file.expandArea", "扩大文件区域")
          }
        >
          {expanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
        </Button>
      </div>
      {preview.isBinary ? (
        <div className="diff-view-state">
          <FileText size={15} />
          <span>
            {t("file.binaryPreviewUnsupported", "二进制文件不支持内容预览")}
          </span>
        </div>
      ) : webLanguage && !preview.contentTruncated ? (
        <WebPreviewBlock
          code={content}
          language={webLanguage}
          variant="panel"
        />
      ) : (
        <CodePreview code={content} relPath={relPath} />
      )}
    </div>
  );
}
