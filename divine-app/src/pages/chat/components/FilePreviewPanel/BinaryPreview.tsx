import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import { fetchPdfPreview } from "@/services/api";
import { getBinaryPreview } from "@/services/tauri";

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
]);

export function isPreviewableBinary(name: string): boolean {
  const dot = name.lastIndexOf(".");
  if (dot < 0) return false;
  return PREVIEWABLE_EXTENSIONS.has(name.slice(dot + 1).toLowerCase());
}

/**
 * Inline preview for binary files. Images render via a base64 data URL; PDFs
 * are rendered to page images by the backend (PyMuPDF) so the webview's native
 * PDF viewer — with its oversized built-in zoom toolbar — never appears.
 */
export function BinaryPreview({ path, fileName }: { path: string; fileName?: string }) {
  const { t } = useTranslation();
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [pdfPages, setPdfPages] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  const isPdf = (fileName ?? "").toLowerCase().endsWith(".pdf");

  useEffect(() => {
    let disposed = false;
    setDataUrl(null);
    setPdfPages(null);
    setError("");
    const load = isPdf
      ? fetchPdfPreview(path).then((result) => {
          if (!disposed) setPdfPages(result.pages);
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
  }, [path, isPdf]);

  if (error) {
    return (
      <div className="diff-view-state error">
        <AlertCircle size={15} />
        <span>{error}</span>
      </div>
    );
  }
  if (isPdf ? !pdfPages : !dataUrl) {
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
  return (
    <div className="binary-preview">
      <img src={dataUrl ?? ""} alt={fileName ?? ""} />
    </div>
  );
}
