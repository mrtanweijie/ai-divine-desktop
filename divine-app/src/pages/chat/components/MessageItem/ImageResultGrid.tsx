// 图像生成结果的卡片缩略图（036 §8）：一行 4 张，点击看大图。
// 只在 tool.tool === "image_generate" 时启用——edit_files / generate_chart
// 那类几十行的文件列表不能跟着变卡片墙。
import { memo, useState } from "react";
import { FolderOpen, Maximize2, MoreHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { Dropdown, type DropdownItem } from "@/components/ui/Dropdown";
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
  const cardActions: DropdownItem[] = [];
  if (rel && onPreviewFile) {
    cardActions.push({
      key: "preview",
      label: t("tool.imagePreview", "查看大图"),
      icon: <Maximize2 size={14} />,
      onClick: () => onPreviewFile({ repoPath: workspacePath ?? "", relPath: rel, fileName }),
    });
  }
  if (isTauri()) {
    cardActions.push({
      key: "reveal",
      label: t("tool.openDirectory", "打开所在目录"),
      icon: <FolderOpen size={14} />,
      onClick: () => void openFileLocation(path),
    });
  }
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
      </div>
      <div className="image-result-meta">
        <div className="image-result-meta-text">
          <span className="image-result-name" title={fileName}>
            {fileName}
          </span>
          <span className="image-result-sub">
            {total > 1 ? `${index + 1}/${total}` : null}
            {total > 1 && dims ? " · " : null}
            {dims ? `${dims.w}×${dims.h}` : null}
          </span>
        </div>
        <Dropdown
          align="end"
          direction="auto"
          openOn="both"
          trigger={
            <Button
              variant="icon"
              size="small"
              aria-label={t("tool.mediaMoreActions", "更多操作")}
              title={t("tool.mediaMoreActions", "更多操作")}
              onClick={(event) => event.stopPropagation()}
            >
              <MoreHorizontal size={15} />
            </Button>
          }
          items={cardActions}
        />
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
  const files = (tool.files ?? []).filter((file) => file.path);
  // 用的哪个模型（后端结果 JSON 的 provider/model，2026-11-04）
  const modelInfo = tool.result as { provider?: string; model?: string } | undefined;
  const modelLabel = [modelInfo?.provider, modelInfo?.model].filter(Boolean).join(" · ");

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
      {modelLabel ? (
        <div className="image-result-model">
          <Tag tone="default">{modelLabel}</Tag>
        </div>
      ) : null}
    </div>
  );
});
