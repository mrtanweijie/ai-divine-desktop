// File download/preview actions: multi-file list and single result file.
import { memo } from "react";
import { Eye, FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { FileTypeIcon } from "@/components/FileTypeIcon";
import { downloadUrl } from "@/services/api";
import { isTauri, openFileLocation } from "@/services/tauri";
import { toWorkspaceRelative } from "@/services/workspace";
import type { PreviewFile, ToolEvent } from "@/types";
import { formatSize } from "@/utils";

/**
 * 一行文件：图标 + 名字 + 体积 + 路径（可选）+「查看改动」。
 *
 * 抽成独立组件是为了让 **A2UI 的 FileList 面板复用它**（044 §4.2 的 S5 追加
 * 说明：FileList 只做 props 转发，不另写一套行样式）。两处唯一的差异是
 * `hidePath` 与有无 `download_url`（面板 IR 里只有工作区相对路径）。
 */
export interface FileRowData {
  name: string;
  path?: string;
  size?: number;
  download_url?: string;
}

export const ToolFileRow = memo(function ToolFileRow({
  file,
  workspacePath,
  onPreviewFile,
  hidePath = false,
}: {
  file: FileRowData;
  workspacePath?: string | null;
  onPreviewFile?: (file: PreviewFile) => void;
  /** 路径与名字重复时（图表统一落在 <workspace>/charts/）不重复展示全路径。 */
  hidePath?: boolean;
}) {
  const { t } = useTranslation();
  const fileRel = file.path && workspacePath ? toWorkspaceRelative(workspacePath, file.path) : null;
  return (
    <div className="file-list-item">
      <a
        className="file-download"
        href={file.download_url ? downloadUrl(file.download_url) : "#"}
        target="_blank"
        rel="noreferrer"
        title={t("tool.openDirectory", "打开所在目录")}
        onClick={(event) => {
          if (file.path && isTauri()) {
            event.preventDefault();
            void openFileLocation(file.path);
          }
        }}
      >
        <FileTypeIcon name={file.path || file.name} />
        <span className="file-name">{file.name}</span>
        {file.size != null && <span className="file-size">{formatSize(file.size)}</span>}
        {file.path && !hidePath && <span className="file-path">{file.path}</span>}
      </a>
      {fileRel && isTauri() && (
        <Button
          variant="icon"
          size="small"
          className="file-preview-button"
          onClick={() =>
            onPreviewFile?.({
              repoPath: workspacePath ?? "",
              relPath: fileRel,
              fileName: file.path?.split("/").pop() ?? file.name,
            })
          }
          title={t("tool.viewChanges", "查看改动")}
          aria-label={t("tool.viewChanges", "查看改动")}
        >
          <Eye size={13} />
        </Button>
      )}
    </div>
  );
});

export const ToolFileList = memo(function ToolFileList({
  tool,
  workspacePath,
  onPreviewFile,
  filesOpen,
  onToggleFiles,
}: {
  tool: ToolEvent;
  workspacePath?: string | null;
  onPreviewFile?: (file: PreviewFile) => void;
  filesOpen: boolean;
  onToggleFiles: () => void;
}) {
  const { t } = useTranslation();
  const files = tool.files ?? [];

  if (files.length === 0) return null;
  // 未展开时最多显示 6 条；展开后（收起型工具经卡片头部、其余经
  // 「展开全部」按钮）显示全部文件。
  return (
    <div className="file-actions file-list">
      {files.slice(0, filesOpen ? files.length : 6).map((file) => (
        <ToolFileRow
          key={file.path ?? file.name}
          file={file}
          workspacePath={workspacePath}
          onPreviewFile={onPreviewFile}
          // 图表 SVG 统一落在 <workspace>/charts/，逐行重复全路径是纯噪音
          hidePath={tool.tool === "generate_chart"}
        />
      ))}
      {files.length > 6 && !filesOpen && (
        <div
          role="button"
          tabIndex={0}
          className="file-list-more"
          onClick={onToggleFiles}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onToggleFiles();
            }
          }}
        >
          {t("tool.expandFiles", "展开全部 {{count}} 个文件", {
            count: files.length,
          })}
        </div>
      )}
    </div>
  );
});

export function ToolResultFile({
  tool,
  workspacePath,
  onPreviewFile,
}: {
  tool: ToolEvent;
  workspacePath?: string | null;
  onPreviewFile?: (file: PreviewFile) => void;
}) {
  const { t } = useTranslation();
  if (tool.status !== "done" || !tool.result?.filepath || tool.files?.length) {
    return null;
  }
  const workspaceRel =
    workspacePath && tool.result.filepath
      ? toWorkspaceRelative(workspacePath, tool.result.filepath)
      : null;
  return (
    <div className="file-actions">
      <a
        className="file-download"
        href={tool.result.download_url ? downloadUrl(tool.result.download_url) : "#"}
        target="_blank"
        rel="noreferrer"
        title={t("tool.openDirectory", "打开所在目录")}
        onClick={(event) => {
          if (tool.result?.filepath && isTauri()) {
            event.preventDefault();
            void openFileLocation(tool.result.filepath);
          }
        }}
      >
        <FolderOpen size={14} />
        <span className="file-name">{tool.result.file_name}</span>
        <span className="file-size">{formatSize(tool.result.file_size)}</span>
      </a>
      {workspaceRel && isTauri() && (
        <Button
          variant="icon"
          size="small"
          className="file-preview-button"
          onClick={() =>
            onPreviewFile?.({
              repoPath: workspacePath ?? "",
              relPath: workspaceRel,
              fileName: tool.result?.file_name,
            })
          }
          title={t("tool.viewChanges", "查看改动")}
          aria-label={t("tool.viewChanges", "查看改动")}
        >
          <Eye size={13} />
        </Button>
      )}
    </div>
  );
}
