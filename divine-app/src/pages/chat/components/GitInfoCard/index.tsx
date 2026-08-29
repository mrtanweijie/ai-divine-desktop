import { memo, useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  GitBranch,
  GitCommitHorizontal,
  ArrowUp,
  ArrowDown,
  Cloud,
  Package,
} from "lucide-react";
import type { PreviewFile } from "@/types";
import { type GitInfo, getGitInfo } from "../../../../services/api";
import "./index.less";

const STATUS_LABEL: Record<string, string> = {
  modified: "Modified",
  added: "Added",
  deleted: "Deleted",
  renamed: "Renamed",
  untracked: "Untracked",
};

const MAX_FILES_SHOWN = 10;

interface GitInfoCardProps {
  projectPath: string;
  onPreviewFile?: (file: PreviewFile) => void;
}

function GitInfoCardContent({
  projectPath,
  onPreviewFile,
  onFileClick,
}: GitInfoCardProps & { onFileClick?: () => void }) {
  const [git, setGit] = useState<GitInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const fetchIdRef = useRef(0);

  useEffect(() => {
    if (!projectPath) {
      setGit(null);
      setLoading(false);
      return;
    }
    const id = ++fetchIdRef.current;
    setLoading(true);
    getGitInfo(projectPath)
      .then((info) => {
        if (id === fetchIdRef.current) {
          setGit(info);
          setLoading(false);
        }
      })
      .catch(() => {
        if (id === fetchIdRef.current) {
          setGit(null);
          setLoading(false);
        }
      });
  }, [projectPath]);

  if (loading) {
    return <div className="git-info-loading">Loading...</div>;
  }

  if (!git || !git.is_git) {
    return null;
  }

  // 按状态分组统计
  const grouped: Record<string, number> = {};
  for (const f of git.files) {
    grouped[f.status] = (grouped[f.status] || 0) + 1;
  }

  return (
    <div className="git-info-content">
      {/* 分支 + ahead/behind */}
      <div className="git-info-row git-info-branch-row">
        <span className="git-info-branch">
          <GitBranch size={13} />
          <span>{git.branch}</span>
        </span>
        <span className="git-info-ahead-behind">
          {git.ahead > 0 && (
            <span className="git-info-ahead">
              <ArrowUp size={11} />
              {git.ahead}
            </span>
          )}
          {git.behind > 0 && (
            <span className="git-info-behind">
              <ArrowDown size={11} />
              {git.behind}
            </span>
          )}
        </span>
      </div>

      {/* 最近提交 */}
      {git.last_commit && (
        <div className="git-info-row git-info-commit">
          <GitCommitHorizontal size={13} />
          <span className="git-info-commit-msg">
            {git.last_commit.message}
          </span>
          <span className="git-info-commit-time">
            {git.last_commit.relative_time}
          </span>
        </div>
      )}

      {/* 远程仓库 */}
      {git.remote_url && (
        <div className="git-info-row git-info-remote">
          <Cloud size={13} />
          <span>{git.remote_url}</span>
        </div>
      )}

      {/* Stash */}
      {git.stash_count > 0 && (
        <div className="git-info-row git-info-stash">
          <Package size={13} />
          <span>
            Stash: {git.stash_count}
          </span>
        </div>
      )}

      {/* 变更文件摘要 */}
      {git.dirty && (
        <>
          <div className="git-info-divider" />
          <div className="git-info-row git-info-status-summary">
            {Object.entries(grouped).map(([status, count]) => (
              <span key={status} className="git-info-status-tag">
                {STATUS_LABEL[status]} · {count}
              </span>
            ))}
          </div>

          {/* 文件列表 */}
          <div className="git-info-files">
            {git.files.slice(0, MAX_FILES_SHOWN).map((f) => (
              <div
                key={f.path}
                className="git-info-file"
                role="button"
                tabIndex={0}
                onClick={() => {
                  onFileClick?.();
                  onPreviewFile?.({
                    repoPath: projectPath,
                    relPath: f.path,
                    fileName: f.path.split("/").pop(),
                  });
                }}
              >
                <span className="git-info-file-path">{f.path}</span>
              </div>
            ))}
            {git.files.length > MAX_FILES_SHOWN && (
              <div className="git-info-files-more">
                +{git.files.length - MAX_FILES_SHOWN} more
              </div>
            )}
          </div>
        </>
      )}

      {/* 无变更 */}
      {!git.dirty && (
        <div className="git-info-row git-info-clean">
          Working tree clean
        </div>
      )}
    </div>
  );
}

/** Git 信息悬停卡片（带 portal 定位） */
export const GitInfoCard = memo(function GitInfoCard({
  projectPath,
  onPreviewFile,
}: GitInfoCardProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const positionCard = useCallback(() => {
    const trigger = triggerRef.current;
    const card = cardRef.current;
    if (!trigger || !card) return;
    const rect = trigger.getBoundingClientRect();
    card.style.position = "fixed";
    card.style.top = `${rect.bottom + 6}px`;
    card.style.right = `${window.innerWidth - rect.right}px`;
  }, []);

  useEffect(() => {
    if (open) {
      positionCard();
      window.addEventListener("resize", positionCard);
      return () => window.removeEventListener("resize", positionCard);
    }
  }, [open, positionCard]);

  const handleEnter = useCallback(() => {
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    setOpen(true);
  }, []);

  const handleLeave = useCallback(() => {
    closeTimerRef.current = setTimeout(() => setOpen(false), 180);
  }, []);

  const handleCardEnter = useCallback(() => {
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
  }, []);

  const handleCardLeave = useCallback(() => {
    closeTimerRef.current = setTimeout(() => setOpen(false), 180);
  }, []);

  return (
    <>
      <span
        ref={triggerRef}
        className="git-info-trigger"
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
        role="button"
        tabIndex={0}
        aria-label="Git project info"
      >
        <GitBranch size={12} />
      </span>
      {open &&
        createPortal(
          <div
            ref={cardRef}
            className="git-info-card"
            onMouseEnter={handleCardEnter}
            onMouseLeave={handleCardLeave}
          >
            <GitInfoCardContent
              projectPath={projectPath}
              onPreviewFile={onPreviewFile}
              onFileClick={() => setOpen(false)}
            />
          </div>,
          document.body
        )}
    </>
  );
});
