import {
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from "react";
import { FileText, Maximize2, Minimize2 } from "lucide-react";
import type { ThemedToken } from "shiki";
import { Button } from "@/components/ui/Button";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import type { FileDiff } from "@/types";
import { useTheme } from "@/services/theme";
import { normalizeLanguage } from "@/pages/chat/components/MarkdownView/language";

interface FileContentViewProps {
  preview: FileDiff;
  relPath: string;
  fileName?: string;
  expanded: boolean;
  onToggleExpand: () => void;
}

function languageFromPath(filePath: string): string | undefined {
  const name = filePath.split("/").pop() ?? filePath;
  if (name === "Dockerfile") return "dockerfile";
  if (name === "Makefile") return "makefile";
  return name.split(".").pop() || undefined;
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
  const content = code || "";
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
        <span>文件内容为空</span>
      </div>
    );
  }

  if (lines === null) {
    return (
      <div className="diff-view-state">
        <LoadingOrb state="searching" size={20} speed={2} />
        <span>加载代码...</span>
      </div>
    );
  }

  const rendered =
    lines.length > 0
      ? lines
      : content.split("\n").map((line) => [{ content: line } as ThemedToken]);

  return (
    <div className="diff-view-code code-preview">
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
  const content = preview.newContent || preview.oldContent || "";
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
          title={expanded ? "缩小文件区域" : "扩大文件区域"}
          aria-label={expanded ? "缩小文件区域" : "扩大文件区域"}
        >
          {expanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
        </Button>
      </div>
      {preview.isBinary ? (
        <div className="diff-view-state">
          <FileText size={15} />
          <span>二进制文件不支持内容预览</span>
        </div>
      ) : (
        <CodePreview code={content} relPath={relPath} />
      )}
    </div>
  );
}
