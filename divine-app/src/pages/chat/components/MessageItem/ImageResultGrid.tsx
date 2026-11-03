// 图像生成结果的卡片缩略图（036 §8）：一行 4 张，点击看大图。
// 只在 tool.tool === "image_generate" 时启用——edit_files / generate_chart
// 那类几十行的文件列表不能跟着变卡片墙。
import { memo, useState } from "react";
import { FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { FileTypeIcon } from "@/components/FileTypeIcon";
import { API_BASE } from "@/services/request";
import { isTauri, openFileLocation } from "@/services/tauri";
import { toWorkspaceRelative } from "@/services/workspace";
import type { PreviewFile, ToolEvent } from "@/types";

function imageUrl(path: string): string {
  return `${API_BASE}/files/image?path=${encodeURIComponent(path)}`;
}

/** 单张卡片：缩略图（contain，不裁切）+ 一行「序号/总数 · 实际尺寸」。 */
const ImageCard = memo(function ImageCard({
  path,
  index,
  total,
  workspacePath,
  onPreviewFile,
}: {
  path: string;
  index: number;
  total: number;
  workspacePath?: string | null;
  onPreviewFile?: (file: PreviewFile) => void;
}) {
  const { t } = useTranslation();
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);
  const fileName = path.split("/").pop() ?? path;
  const rel = workspacePath ? toWorkspaceRelative(workspacePath, path) : null;
  return (
    <div
      className={`image-result-card${total === 1 ? " is-single" : ""}`}
      role={rel ? "button" : undefined}
      tabIndex={rel ? 0 : undefined}
      onClick={
        rel && onPreviewFile
          ? () =>
              onPreviewFile({
                repoPath: workspacePath ?? "",
                relPath: rel,
                fileName,
              })
          : undefined
      }
      onKeyDown={
        rel
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onPreviewFile?.({
                  repoPath: workspacePath ?? "",
                  relPath: rel,
                  fileName,
                });
              }
            }
          : undefined
      }
    >
      <div className="image-result-thumb">
        <img
          src={imageUrl(path)}
          alt={fileName}
          loading="lazy"
          decoding="async"
          onLoad={(event) => {
            const img = event.currentTarget;
            if (img.naturalWidth > 0) {
              setDims({ w: img.naturalWidth, h: img.naturalHeight });
            }
          }}
        />
        {isTauri() && (
          <Button
            variant="icon"
            size="small"
            className="image-result-open"
            title={t("tool.openDirectory", "打开所在目录")}
            aria-label={t("tool.openDirectory", "打开所在目录")}
            onClick={(event) => {
              event.stopPropagation();
              void openFileLocation(path);
            }}
          >
            <FolderOpen size={13} />
          </Button>
        )}
      </div>
      <div className="image-result-meta">
        <FileTypeIcon name={fileName} />
        <span>
          {total > 1 ? `${index + 1}/${total}` : fileName}
          {dims ? ` · ${dims.w}×${dims.h}` : ""}
        </span>
      </div>
    </div>
  );
});

export const ImageResultGrid = memo(function ImageResultGrid({
  tool,
  workspacePath,
  onPreviewFile,
}: {
  tool: ToolEvent;
  workspacePath?: string | null;
  onPreviewFile?: (file: PreviewFile) => void;
}) {
  const { t } = useTranslation();
  const [listOpen, setListOpen] = useState(false);
  const files = (tool.files ?? []).filter((file) => file.path);

  if (files.length === 0) return null;

  return (
    <div className="image-result">
      <div className={`image-result-grid${files.length === 1 ? " is-single" : ""}`}>
        {files.map((file, index) => (
          <ImageCard
            key={file.path}
            path={file.path as string}
            index={index}
            total={files.length}
            workspacePath={workspacePath}
            onPreviewFile={onPreviewFile}
          />
        ))}
      </div>
      {/* 文件列表折叠入口：要按文件名/路径找图的用户仍然拿得到 */}
      <div
        role="button"
        tabIndex={0}
        className="image-result-toggle"
        onClick={() => setListOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setListOpen((value) => !value);
          }
        }}
      >
        {listOpen ? t("tool.imageHideList", "收起文件列表") : t("tool.imageShowList", "文件列表")}
      </div>
      {listOpen && (
        <div className="file-actions file-list">
          {files.map((file) => (
            <div key={file.path} className="file-list-item">
              <span className="file-download">
                <FileTypeIcon name={file.path || file.name} />
                <span className="file-name">{file.name}</span>
                <span className="file-path">{file.path}</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
