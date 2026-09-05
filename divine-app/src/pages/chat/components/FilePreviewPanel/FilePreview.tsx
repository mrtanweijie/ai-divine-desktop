import { useCallback, useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import {
  getExternalFilePreview,
  getFileDiff,
  isTauri,
  listenWorkspaceChanges,
} from "@/services/tauri";
import { workspaceJoin } from "@/services/workspace";
import type { FileDiff } from "@/types";
import { DiffView } from "./DiffView";
import { FileContentView } from "./FileContentView";

interface FilePreviewProps {
  repoPath: string;
  relPath: string;
  absolutePath?: string;
  content?: string;
  fileName?: string;
  changed: boolean;
}

function normalizePath(value: string): string {
  return value.replace(/\\/g, "/").replace(/\/+$/, "");
}

export function FilePreview({
  repoPath,
  relPath,
  absolutePath,
  content,
  fileName,
  changed,
}: FilePreviewProps) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<FileDiff | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(
    async (showLoading: boolean) => {
      if (!isTauri()) return;
      if (showLoading) setLoading(true);
      setError("");
      try {
        if (absolutePath) {
          setPreview(await getExternalFilePreview(absolutePath));
        } else if (content !== undefined) {
          setPreview({
            relPath,
            oldContent: "",
            newContent: content,
            diffText: "",
            additions: 0,
            deletions: 0,
            isGit: false,
            tracked: true,
            isBinary: false,
            exists: true,
            contentTruncated: false,
          });
        } else {
          setPreview(await getFileDiff(repoPath, relPath));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setPreview(null);
      } finally {
        if (showLoading) setLoading(false);
      }
    },
    [absolutePath, content, relPath, repoPath],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 挂载/路径变化触发数据加载，setState 在 await 之后
    void load(true);
  }, [absolutePath, content, load, relPath]);

  useEffect(() => {
    if (!isTauri()) return;
    if (absolutePath) return;
    let disposed = false;
    let unlisten: (() => void) | undefined;
    const targetPath = normalizePath(workspaceJoin(repoPath, relPath));

    void listenWorkspaceChanges((payload) => {
      if (disposed) return;
      if (normalizePath(payload.path) !== targetPath) return;
      window.setTimeout(() => {
        if (!disposed) void load(false);
      }, 180);
    }).then((stop) => {
      if (disposed) stop();
      else unlisten = stop;
    });

    const pollTimer = window.setInterval(() => {
      if (!disposed) void load(false);
    }, 2500);

    return () => {
      disposed = true;
      window.clearInterval(pollTimer);
      unlisten?.();
    };
  }, [absolutePath, content, load, relPath, repoPath]);

  if (loading) {
    return (
      <div className="diff-view">
        <div className="diff-view-state">
          <LoadingOrb state="searching" size={20} speed={2} />
          <span>{t("file.readingFile", "读取文件...")}</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="diff-view">
        <div className="diff-view-head">
          <span className="diff-view-file">{fileName ?? relPath}</span>
        </div>
        <div className="diff-view-state error">
          <AlertCircle size={15} />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="diff-view">
        <div className="diff-view-state">
          <span>{t("file.noReadableContent", "没有可读取的内容")}</span>
        </div>
      </div>
    );
  }

  const hasChanges = Boolean(
    changed ||
    (!preview.isBinary &&
      (preview.diffText.trim() ||
        (preview.isGit && !preview.tracked && Boolean(preview.newContent)) ||
        (!preview.exists && Boolean(preview.oldContent)))),
  );

  // Absolute path used by the binary inline preview (image/PDF).
  const filePath = absolutePath ?? workspaceJoin(repoPath, relPath);

  if (hasChanges) {
    return (
      <DiffView
        preview={preview}
        relPath={relPath}
        fileName={fileName}
        path={filePath}
        changed={changed}
      />
    );
  }
  return (
    <FileContentView preview={preview} relPath={relPath} fileName={fileName} path={filePath} />
  );
}
