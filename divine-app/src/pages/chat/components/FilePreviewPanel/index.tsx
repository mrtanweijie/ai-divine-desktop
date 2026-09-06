import { memo, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Check, ChevronRight, ListTree, Maximize2, Minimize2, PanelRightClose } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import { openFileLocation } from "@/services/tauri";
import { toast } from "@/components/ui/Toast";
import type { PreviewFile } from "@/types";
import { FilePreview } from "./FilePreview";
import { FileTree } from "./FileTree";
import { PreviewHeaderSlot, PreviewHeaderSlotProvider } from "./PreviewHeaderSlot";
import "./index.less";

// 拖拽文件树分隔条：低于该宽度直接收起；收起态拖拽越过该位移后先还原到最小宽度
const TREE_COLLAPSE_WIDTH = 140;
const TREE_EXPAND_THRESHOLD = 24;

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
  const [treeCollapsed, setTreeCollapsed] = useState(false);
  const [treeAnimating, setTreeAnimating] = useState(false);
  const treeAnimTimer = useRef<number | undefined>(undefined);

  // 程序化收起/展开（拖拽越过阈值、点击悬浮按钮）：走 200ms 过渡；
  // 拖拽本身保持即时跟手，拖拽开始时先终止未完成的动画。
  const runTreeAnim = (nextCollapsed: boolean) => {
    if (treeAnimTimer.current !== undefined) {
      window.clearTimeout(treeAnimTimer.current);
    }
    setTreeAnimating(true);
    setTreeCollapsed(nextCollapsed);
    if (!nextCollapsed) {
      onTreeWidthChange(TREE_COLLAPSE_WIDTH);
    }
    treeAnimTimer.current = window.setTimeout(() => {
      setTreeAnimating(false);
      treeAnimTimer.current = undefined;
    }, 220);
  };
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

  // 头部文件名点击 → 在系统文件管理器中打开文件所在目录。
  // 树选择/tool 结果构造的 PreviewFile 可能没有绝对 path，
  // 用 repoPath + relPath 兜底拼接；失败以 Toast 提示（不静默）。
  const handleOpenContainingFolder = () => {
    if (!selectedFile) return;
    const absPath =
      selectedFile.path ??
      (repoPath && selectedFile.relPath
        ? `${repoPath.replace(/\/+$/, "")}/${selectedFile.relPath.replace(/^\//, "")}`
        : "");
    if (!absPath) return;
    openFileLocation(absPath).catch(() => {
      toast.error(t("file.openFolderFailed", "打开目录失败，文件可能已被移动或删除"));
    });
  };

  if (!repoPath) return null;

  const handleResizeStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    setResizing(true);
    const startX = event.clientX;
    const startWidth = width;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMove = (moveEvent: PointerEvent) => {
      const nextWidth = Math.min(760, Math.max(320, startWidth + startX - moveEvent.clientX));
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

  const handleTreeResizeStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    // 拖拽以即时跟手优先：终止可能未完成的收起/展开动画
    if (treeAnimTimer.current !== undefined) {
      window.clearTimeout(treeAnimTimer.current);
      treeAnimTimer.current = undefined;
    }
    setTreeAnimating(false);
    // 拖拽过程中的局部模式记录：state 更新是异步的，同一次拖拽内以局部变量为准
    let mode: "normal" | "collapsed" = treeCollapsed ? "collapsed" : "normal";
    let base = treeCollapsed ? 0 : treeWidth;
    let baseDx = 0;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMove = (moveEvent: PointerEvent) => {
      const dx = moveEvent.clientX - startX;
      if (mode === "collapsed") {
        // 收起态向右拖：越过阈值后先还原到 140px，继续拖则跟手变宽
        if (dx >= TREE_EXPAND_THRESHOLD) {
          mode = "normal";
          base = TREE_COLLAPSE_WIDTH;
          baseDx = dx;
          setTreeCollapsed(false);
          onTreeWidthChange(TREE_COLLAPSE_WIDTH);
        }
        return;
      }
      // 拖到 140px 以下：带动画收起（父层宽度保留，作为还原前的记忆宽度）
      const nextWidth = base + dx - baseDx;
      if (nextWidth < TREE_COLLAPSE_WIDTH) {
        mode = "collapsed";
        runTreeAnim(true);
        return;
      }
      onTreeWidthChange(Math.min(320, nextWidth));
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
    <PreviewHeaderSlotProvider>
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
          <div className="file-inspector-title-group">
            <span className="file-inspector-title">{t("file.title", "文件")}</span>
            {selectedFile && (
              <>
                <ChevronRight size={12} className="file-inspector-crumb-sep" />
                <div
                  role="button"
                  tabIndex={0}
                  className="file-inspector-crumb"
                  title={`${t("chat.openFileLocation", "打开所在目录")} · ${selectedFile.relPath}`}
                  onClick={handleOpenContainingFolder}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      handleOpenContainingFolder();
                    }
                  }}
                >
                  <span className="file-inspector-crumb-name">
                    {selectedFile.fileName ?? selectedFile.relPath}
                  </span>
                </div>
                {onAcceptFile && changedFiles.has(selectedFile.relPath) && (
                  <Button
                    variant="ghost"
                    size="small"
                    className="diff-accept-button"
                    onClick={() => onAcceptFile(selectedFile.relPath)}
                    title={t("file.acceptChanges", "接受变更，清除蓝点")}
                  >
                    <Check size={13} />
                    {t("common.accept", "接受")}
                  </Button>
                )}
              </>
            )}
          </div>
          <div className="file-inspector-actions">
            <PreviewHeaderSlot />
            {(expanded || selectedFile) && (
              <IconButton
                icon={expanded ? <Minimize2 size={11} /> : <Maximize2 size={11} />}
                title={
                  expanded
                    ? t("file.shrinkArea", "缩小文件区域")
                    : t("file.expandArea", "扩大文件区域")
                }
                onClick={onToggleExpand}
              />
            )}
            {!expanded && (
              <IconButton
                icon={<PanelRightClose size={14} />}
                title={t("file.collapsePanel", "收起面板")}
                onClick={onClose}
              />
            )}
          </div>
        </header>
        <div
          className={`file-inspector-body${
            treeCollapsed ? " is-tree-collapsed" : ""
          }${treeAnimating ? " is-tree-animating" : ""}`}
        >
          {treeCollapsed && (
            <span className="file-tree-expand-fab">
              <IconButton
                icon={<ListTree size={13} />}
                title={t("file.expandTree", "展开文件树")}
                onClick={() => runTreeAnim(false)}
              />
            </span>
          )}
          <FileTree
            repoPath={repoPath}
            changedFiles={changedFiles}
            selectedPath={selectedFile?.relPath ?? null}
            width={treeCollapsed ? 0 : treeWidth}
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
            style={{ left: treeCollapsed ? 0 : treeWidth - 2 }}
            onPointerDown={handleTreeResizeStart}
            title={
              treeCollapsed
                ? t("file.dragExpandTree", "向右拖拽展开文件树")
                : t("file.dragResizeTree", "拖拽调整文件树宽度")
            }
            aria-label={
              treeCollapsed
                ? t("file.dragExpandTree", "向右拖拽展开文件树")
                : t("file.dragResizeTree", "拖拽调整文件树宽度")
            }
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
              />
            ) : (
              <div className="file-inspector-empty">
                <span>{t("file.selectFromLeft", "从左侧选择文件查看改动")}</span>
              </div>
            )}
          </div>
        </div>
      </aside>
    </PreviewHeaderSlotProvider>
  );
}

export const FilePreviewPanel = memo(FilePreviewPanelInner);
