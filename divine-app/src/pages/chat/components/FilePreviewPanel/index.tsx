import {
  useEffect,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { Minimize2, PanelRightClose } from "lucide-react";
import { Button } from "@/components/ui/Button";
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

export function FilePreviewPanel({
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
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(open);
  const [resizing, setResizing] = useState(false);

  useEffect(() => {
    if (open) {
      setMounted(true);
      setVisible(true);
      return;
    }
    setVisible(false);
  }, [open]);

  if (!mounted || !repoPath) return null;

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
      className={`file-inspector-panel ${visible ? "is-open" : "is-closing"}${
        resizing ? " is-resizing" : ""
      }${expanded ? " is-expanded" : ""}`}
      style={{
        width: visible ? (expanded ? "auto" : width) : 0,
        minWidth: visible ? (expanded ? 0 : 320) : 0,
        transition: noTransition ? "none" : undefined,
      }}
    >
      <div
        className="file-inspector-resizer"
        onPointerDown={handleResizeStart}
        title="拖拽调整宽度"
        aria-label="拖拽调整宽度"
      />
      <header className="file-inspector-header">
        <span className="file-inspector-title">文件</span>
        <div className="file-inspector-actions">
          {!expanded && (
            <Button
              variant="icon"
              size="small"
              onClick={onClose}
              title="收起面板"
              aria-label="收起面板"
            >
              <PanelRightClose size={14} />
            </Button>
          )}
          {expanded && !selectedFile && (
            <Button
              variant="icon"
              size="small"
              onClick={onToggleExpand}
              title="缩小文件区域"
              aria-label="缩小文件区域"
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
          title="拖拽调整文件树宽度"
          aria-label="拖拽调整文件树宽度"
        />
        <div className="file-inspector-preview">
          {selectedFile ? (
            <FilePreview
              key={selectedFile.relPath}
              repoPath={selectedFile.repoPath}
              relPath={selectedFile.relPath}
              fileName={selectedFile.fileName}
              changed={changedFiles.has(selectedFile.relPath)}
              onAcceptFile={onAcceptFile}
              expanded={expanded}
              onToggleExpand={onToggleExpand}
            />
          ) : (
            <div className="file-inspector-empty">
              <span>从左侧选择文件查看改动</span>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
