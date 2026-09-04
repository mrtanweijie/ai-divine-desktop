import { useState } from "react";
import { Check, Code2, Copy, Eye } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { toast } from "@/components/ui/Toast";
import { copyText } from "@/utils";
import { HighlightedCode } from "./HighlightedCode";
import { MarkdownView } from "./index";
import {
  PreviewHeaderActions,
  usePreviewHeaderHosted,
} from "@/pages/chat/components/FilePreviewPanel/PreviewHeaderSlot";

export type MarkdownPreviewVariant = "chat" | "panel";

interface MarkdownPreviewBlockProps {
  code: string;
  variant?: MarkdownPreviewVariant;
  defaultMode?: MarkdownPreviewMode;
}

type MarkdownPreviewMode = "preview" | "source";

/** 与 WebPreviewBlock 一致：按 缓存用户上次选择的查看模式，切换文件后回来不丢。 */
const modeCache = new Map<string, MarkdownPreviewMode>();

/**
 * Markdown 文件预览块（对齐 WebPreviewBlock 的交互模式）：
 * 默认渲染 Markdown 成品视图，可一键切换回原始文本（shiki 高亮）。
 * 复用 .web-preview-block 结构与样式，通过 .md 修饰类做背景/滚动适配。
 */
export function MarkdownPreviewBlock({
  code,
  variant = "chat",
  defaultMode = "preview",
}: MarkdownPreviewBlockProps) {
  const { t } = useTranslation();
  const cacheKey = `${variant}\u0000${code}`;
  const [mode, setMode] = useState<MarkdownPreviewMode>(
    () => modeCache.get(cacheKey) ?? defaultMode
  );
  const [copied, setCopied] = useState(false);

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

  // 面板宿主内：动作按钮注册到面板头部（PreviewHeaderSlot），本块不再渲染头行；
  // 聊天消息侧（无宿主）：保留原有自带头部
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
    <div className={`web-preview-block md ${variant}`}>
      {hosted ? (
        <PreviewHeaderActions>
          <span className="diff-view-head-actions">{actionButtons}</span>
        </PreviewHeaderActions>
      ) : (
        <div className="web-preview-header">
          <span className="web-preview-title">
            {t("markdown.mdPreview", "Markdown 预览")}
          </span>
          <div className="web-preview-actions">{actionButtons}</div>
        </div>
      )}
      {mode === "source" ? (
        <pre className="web-preview-source">
          <HighlightedCode code={code} language="markdown" streaming={false} />
        </pre>
      ) : (
        <div className="web-preview-frame md-preview-frame">
          <div className="md-preview-scroll">
            <MarkdownView content={code} streaming={false} />
          </div>
        </div>
      )}
    </div>
  );
}
