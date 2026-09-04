import { useEffect, useState } from "react";
import { AlertCircle, Check, Code2, Copy, Eye } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import { toast } from "@/components/ui/Toast";
import { copyText } from "@/utils";
import { fetchPdfPreview, fetchDocumentPreview } from "@/services/api";
import { getBinaryPreview } from "@/services/tauri";
import { MarkdownView } from "@/pages/chat/components/MarkdownView";
import { PreviewHeaderActions } from "./PreviewHeaderSlot";

const PREVIEWABLE_EXTENSIONS = new Set([
  "png",
  "jpg",
  "jpeg",
  "gif",
  "webp",
  "svg",
  "bmp",
  "avif",
  "pdf",
  "doc", "docx", "docm",
  "xls", "xlsx", "xlsm", "xlsb",
  "ppt", "pptx", "pptm", "ppsx", "ppsm",
  "odt", "ods", "odp",
  "csv", "rtf", "epub",
]);

export function isPreviewableBinary(name: string): boolean {
  const dot = name.lastIndexOf(".");
  if (dot < 0) return false;
  return PREVIEWABLE_EXTENSIONS.has(name.slice(dot + 1).toLowerCase());
}

const DOCUMENT_EXTENSIONS = new Set([
  "doc", "docx", "docm",
  "xls", "xlsx", "xlsm", "xlsb",
  "ppt", "pptx", "pptm", "ppsx", "ppsm",
  "odt", "ods", "odp",
  "csv", "rtf", "epub",
]);

function getExt(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot + 1).toLowerCase();
}

type DocPreviewMode = "preview" | "source";

function DocumentPreview({
  content,
}: {
  content: string;
  fileName?: string;
}) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<DocPreviewMode>("preview");
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await copyText(content);
    setCopied(true);
    toast.success(t("markdown.webSourceCopied", "源码已复制"));
    setTimeout(() => setCopied(false), 1200);
  };
  const toggleMode = () => setMode(mode === "preview" ? "source" : "preview");

  return (
    <div className="binary-preview document-preview">
      {/* 动作按钮注册到外层 diff-view-head，避免双行头部 */}
      <PreviewHeaderActions>
        <span className="diff-view-head-actions">
          <Button
            variant="icon"
            size="small"
            onClick={toggleMode}
            title={
              mode === "preview"
                ? t("markdown.viewSource", "查看源码")
                : t("markdown.viewPreview", "查看预览")
            }
            aria-label={
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
            onClick={copy}
            title={
              copied ? t("common.copied", "已复制") : t("markdown.copy", "复制")
            }
            aria-label={
              copied ? t("common.copied", "已复制") : t("markdown.copy", "复制")
            }
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </Button>
        </span>
      </PreviewHeaderActions>
      <div className="document-preview-content">
        {mode === "preview" ? (
          <MarkdownView content={content} streaming={false} />
        ) : (
          <pre className="document-preview-source">{content}</pre>
        )}
      </div>
    </div>
  );
}

/**
 * Inline preview for binary files. Images render via a base64 data URL; PDFs
 * are rendered to page images by the backend (PyMuPDF); Word/Excel/CSV files
 * are converted to Markdown by the backend and rendered as rich text.
 */
export function BinaryPreview({ path, fileName }: { path: string; fileName?: string }) {
  const { t } = useTranslation();
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [pdfPages, setPdfPages] = useState<string[] | null>(null);
  const [docContent, setDocContent] = useState<string | null>(null);
  const [error, setError] = useState("");
  const ext = getExt(fileName ?? path);
  const isPdf = ext === "pdf";
  const isDocument = DOCUMENT_EXTENSIONS.has(ext);

  useEffect(() => {
    let disposed = false;
    setDataUrl(null);
    setPdfPages(null);
    setDocContent(null);
    setError("");
    const load = isPdf
      ? fetchPdfPreview(path).then((result) => {
          if (!disposed) setPdfPages(result.pages);
        })
      : isDocument
        ? fetchDocumentPreview(path).then((result) => {
            if (!disposed) setDocContent(result.content);
          })
        : getBinaryPreview(path).then((result) => {
            if (!disposed) setDataUrl(result.dataUrl);
          });
    load.catch((err: unknown) => {
      if (!disposed) {
        setError(err instanceof Error ? err.message : String(err));
      }
    });
    return () => {
      disposed = true;
    };
  }, [path, isPdf, isDocument]);

  if (error) {
    return (
      <div className="diff-view-state error">
        <AlertCircle size={15} />
        <span>{error}</span>
      </div>
    );
  }
  if (isPdf ? !pdfPages : isDocument ? !docContent : !dataUrl) {
    return (
      <div className="diff-view-state">
        <LoadingOrb state="searching" size={20} speed={2} />
        <span>{t("file.readingFile", "读取文件...")}</span>
      </div>
    );
  }
  if (pdfPages) {
    return (
      <div className="binary-preview pdf-preview">
        {pdfPages.map((page, index) => (
          <img key={index} src={page} alt={`${fileName ?? "PDF"} 第 ${index + 1} 页`} />
        ))}
      </div>
    );
  }
  if (docContent !== null) {
    return (
      <DocumentPreview content={docContent} />
    );
  }
  return (
    <div className="binary-preview">
      <img src={dataUrl ?? ""} alt={fileName ?? ""} />
    </div>
  );
}
