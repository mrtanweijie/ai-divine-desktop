import {
  memo,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { Minimize2, PanelRightClose } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import type { PreviewFile } from "@/types";
import { FilePreview } from "./FilePreview";
import { FileTree } from "./FileTree";
import "./index.less";

interface FilePreviewPanelProps {
  open: boolean;
  repoPath: string;
  selectedFile: PreviewFile | null;
  changedFiles: ReadonlySet<string>;
  width: number;
  onWidthChange: (width: number) => void;
  treeWidth: number;
  onTreeWidthChange: (width: number) => void;
  expanded: boolean;
  onToggleExpand: () => void;
  noTransition: boolean;
  onClose: () => void;
  onSelectFile: (file: PreviewFile) => void;
  onAcceptFile: (relPath: string) => void;
}

export function FilePreviewPanelInner({
  open,
  repoPath,
  selectedFile,
  changedFiles,
  width,
  onWidthChange,
  treeWidth,
  onTreeWidthChange,
  expanded,
  onToggleExpand,
  noTransition,
  onClose,
  onSelectFile,
  onAcceptFile,
}: FilePreviewPanelProps) {
  const { t } = useTranslation();
  const [resizing, setResizing] = useState(false);
  const [expandTo, setExpandTo] = useState<string | null>(null);
  const expandToPrevRef = useRef<string | null>(null);

  // selectedFile 变化时触发文件树展开（仅在路径真正变化时）
  useEffect(() => {
    const next = selectedFile?.relPath ?? null;
    if (next !== expandToPrevRef.current) {
      expandToPrevRef.current = next;
      setExpandTo(next);
    }
  }, [selectedFile?.relPath]);

  if (!repoPath) return null;

  const handleResizeStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    setResizing(true);
    const startX = event.clientX;
    const startWidth = width;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMove = (moveEvent: PointerEvent) => {
      const nextWidth = Math.min(
        760,
        Math.max(320, startWidth + startX - moveEvent.clientX)
      );
      onWidthChange(nextWidth);
    };
    const onUp = () => {
      setResizing(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  const handleTreeResizeStart = (
    event: ReactPointerEvent<HTMLDivElement>
  ) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = treeWidth;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMove = (moveEvent: PointerEvent) => {
      const nextWidth = Math.min(
        320,
        Math.max(140, startWidth + moveEvent.clientX - startX)
      );
      onTreeWidthChange(nextWidth);
    };
    const onUp = () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <aside
      className={`file-inspector-panel ${open ? "is-open" : "is-closing"}${
        resizing ? " is-resizing" : ""
      }${expanded ? " is-expanded" : ""}`}
      style={{
        width: open ? (expanded ? "auto" : width) : 0,
        minWidth: open ? (expanded ? 0 : 320) : 0,
        transition: noTransition ? "none" : undefined,
      }}
    >
      <div
        className="file-inspector-resizer"
        onPointerDown={handleResizeStart}
        title={t("file.dragResizeWidth", "拖拽调整宽度")}
        aria-label={t("file.dragResizeWidth", "拖拽调整宽度")}
      />
      <header className="file-inspector-header">
        <span className="file-inspector-title">{t("file.title", "文件")}</span>
        <div className="file-inspector-actions">
          {!expanded && (
            <IconButton
              icon={<PanelRightClose size={13} />}
              title={t("file.collapsePanel", "收起面板")}
              onClick={onClose}
            />
          )}
          {expanded && !selectedFile && (
            <Button
              variant="icon"
              size="small"
              onClick={onToggleExpand}
              title={t("file.shrinkArea", "缩小文件区域")}
              aria-label={t("file.shrinkArea", "缩小文件区域")}
            >
              <Minimize2 size={14} />
            </Button>
          )}
        </div>
      </header>
      <div className="file-inspector-body">
        <FileTree
          repoPath={repoPath}
          changedFiles={changedFiles}
          selectedPath={selectedFile?.relPath ?? null}
          width={treeWidth}
          expandTo={expandTo}
          onSelectFile={(relPath) =>
            onSelectFile({
              repoPath,
              relPath,
              fileName: relPath.split("/").pop(),
            })
          }
        />
        <div
          className="file-tree-resizer"
          style={{ left: treeWidth - 2 }}
          onPointerDown={handleTreeResizeStart}
          title={t("file.dragResizeTree", "拖拽调整文件树宽度")}
          aria-label={t("file.dragResizeTree", "拖拽调整文件树宽度")}
        />
        <div className="file-inspector-preview">
          {selectedFile ? (
            <FilePreview
              key={`${selectedFile.relPath}-${selectedFile.path ?? ""}`}
              repoPath={selectedFile.repoPath}
              relPath={selectedFile.relPath}
              absolutePath={selectedFile.path}
              content={selectedFile.content}
              fileName={selectedFile.fileName}
              changed={changedFiles.has(selectedFile.relPath)}
              onAcceptFile={onAcceptFile}
              expanded={expanded}
              onToggleExpand={onToggleExpand}
            />
          ) : (
            <div className="file-inspector-empty">
              <span>{t("file.selectFromLeft", "从左侧选择文件查看改动")}</span>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

export const FilePreviewPanel = memo(FilePreviewPanelInner);
