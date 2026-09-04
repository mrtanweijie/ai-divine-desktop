import { useMemo, useState } from "react";
import { Check, Code2, Copy, Eye } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { toast } from "@/components/ui/Toast";
import { copyText } from "@/utils";
import { HighlightedCode } from "./HighlightedCode";
import {
  PreviewHeaderActions,
  usePreviewHeaderHosted,
} from "@/pages/chat/components/FilePreviewPanel/PreviewHeaderSlot";

export type WebPreviewLanguage = "html" | "svg";
export type WebPreviewVariant = "chat" | "panel";

interface WebPreviewBlockProps {
  code: string;
  language: WebPreviewLanguage;
  variant?: WebPreviewVariant;
  defaultMode?: PreviewMode;
}

type PreviewMode = "preview" | "source";

const modeCache = new Map<string, PreviewMode>();

function isCompleteDocument(code: string, language: WebPreviewLanguage): boolean {
  const trimmed = code.trim().toLowerCase();
  if (language === "html") {
    return (
      trimmed.startsWith("<!doctype html") ||
      trimmed.startsWith("<html") ||
      trimmed.startsWith("<html ")
    );
  }
  return false;
}

function buildPreviewDocument(
  code: string,
  language: WebPreviewLanguage
): string {
  if (isCompleteDocument(code, language)) {
    return code;
  }
  if (language === "svg") {
    return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <style>
  html, body {
    height: 100%;
    margin: 0;
    overflow: auto;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
  }
  svg {
    max-width: 100%;
    max-height: 100%;
    height: auto;
    display: block;
  }
</style>
  </head>
  <body>
    ${code}
  </body>
</html>`;
  }
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
  </head>
  <body style="margin:0">
    ${code}
  </body>
</html>`;
}

export function WebPreviewBlock({
  code,
  language,
  variant = "chat",
  defaultMode = "source",
}: WebPreviewBlockProps) {
  const { t } = useTranslation();
  const cacheKey = `${variant}\u0000${language}\u0000${code}`;
  const [mode, setMode] = useState<PreviewMode>(
    () => modeCache.get(cacheKey) ?? defaultMode
  );
  const [copied, setCopied] = useState(false);
  const srcDoc = useMemo(
    () => buildPreviewDocument(code, language),
    [code, language]
  );
  const title =
    language === "html"
      ? t("markdown.htmlPreview", "HTML 预览")
      : t("markdown.svgPreview", "SVG 预览");

  const copy = async () => {
    await copyText(code);
    setCopied(true);
    toast.success(t("markdown.webSourceCopied", "源码已复制"));
    setTimeout(() => setCopied(false), 1200);
  };
  const toggleMode = () => {
    const next = mode === "preview" ? "source" : "preview";
    modeCache.set(cacheKey, next);
    setMode(next);
  };

  // 面板宿主内：动作按钮注册到面板头部，本块不再渲染头行；聊天侧保留自带头部
  const hosted = usePreviewHeaderHosted();
  const actionButtons = (
    <>
      <Button
        variant="icon"
        size="small"
        type="button"
        className="web-preview-toggle"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          toggleMode();
        }}
        aria-label={
          mode === "preview"
            ? t("markdown.viewSource", "查看源码")
            : t("markdown.viewPreview", "查看预览")
        }
        title={
          mode === "preview"
            ? t("markdown.viewSource", "查看源码")
            : t("markdown.viewPreview", "查看预览")
        }
      >
        {mode === "preview" ? <Code2 size={13} /> : <Eye size={13} />}
      </Button>
      <Button
        variant="icon"
        size="small"
        type="button"
        className="web-preview-copy"
        onClick={copy}
        aria-label={t("markdown.copyCode", "复制代码")}
        title={
          copied ? t("common.copied", "已复制") : t("markdown.copy", "复制")
        }
      >
        {copied ? <Check size={13} /> : <Copy size={13} />}
      </Button>
    </>
  );

  return (
    <div className={`web-preview-block ${language} ${variant}`}>
      {hosted ? (
        <PreviewHeaderActions>
          <span className="diff-view-head-actions">{actionButtons}</span>
        </PreviewHeaderActions>
      ) : (
        <div className="web-preview-header">
          <span className="web-preview-title">{title}</span>
          <div className="web-preview-actions">{actionButtons}</div>
        </div>
      )}
      {mode === "source" ? (
        <pre className="web-preview-source">
          <HighlightedCode
            code={code}
            language={language === "svg" ? "svg" : "html"}
            streaming={false}
          />
        </pre>
      ) : (
        <div className="web-preview-frame">
          <iframe
            title={title}
            sandbox="allow-scripts allow-forms allow-modals allow-downloads"
            referrerPolicy="no-referrer"
            srcDoc={srcDoc}
          />
        </div>
      )}
    </div>
  );
}
