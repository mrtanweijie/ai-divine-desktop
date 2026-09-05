import { useEffect, useRef, useState } from "react";
import {
  Braces,
  ChevronRight,
  Database,
  FileArchive,
  FileCode,
  FileCog,
  FileImage,
  FileKey,
  FileMusic,
  FileSpreadsheet,
  FileTerminal,
  FileText,
  FileVideoCamera,
  Folder,
  FolderOpen,
  Presentation,
} from "lucide-react";
import { getDirChildren, getFileTree, isTauri, listenWorkspaceChanges } from "@/services/tauri";
import { useTranslation } from "react-i18next";
import type { WorkspaceFileNode } from "@/types";

const treeCache = new Map<string, WorkspaceFileNode[]>();
const dirCache = new Map<string, WorkspaceFileNode[]>();

function normalizePath(value: string): string {
  return value.replace(/\\/g, "/").replace(/\/+$/, "");
}

interface FileTreeProps {
  repoPath: string;
  changedFiles: ReadonlySet<string>;
  selectedPath: string | null;
  onSelectFile: (relPath: string) => void;
  width: number;
  expandTo?: string | null;
}

interface TreeNodeProps {
  node: WorkspaceFileNode;
  repoPath: string;
  changedFiles: ReadonlySet<string>;
  selectedPath: string | null;
  onSelectFile: (relPath: string) => void;
  depth: number;
  expandTo?: string | null;
}

function fileIcon(name: string) {
  const lower = name.toLowerCase();
  const ext = lower.split(".").pop() ?? "";

  if (
    name === "Dockerfile" ||
    name === "Makefile" ||
    lower === "dockerfile" ||
    lower === "makefile"
  ) {
    return <FileCog size={14} />;
  }
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "ico", "avif"].includes(ext)) {
    return <FileImage size={14} />;
  }
  if (["zip", "tar", "gz", "7z", "rar", "xz", "bz2"].includes(ext)) {
    return <FileArchive size={14} />;
  }
  if (["mp3", "wav", "flac", "aac", "ogg", "m4a"].includes(ext)) {
    return <FileMusic size={14} />;
  }
  if (["mp4", "mov", "avi", "mkv", "webm", "flv"].includes(ext)) {
    return <FileVideoCamera size={14} />;
  }
  if (["xlsx", "xls", "csv", "tsv"].includes(ext)) {
    return <FileSpreadsheet size={14} />;
  }
  if (["ppt", "pptx", "key"].includes(ext)) {
    return <Presentation size={14} />;
  }
  if (["db", "sqlite", "sqlite3", "sql"].includes(ext)) {
    return <Database size={14} />;
  }
  if (["sh", "bash", "zsh", "ps1", "bat", "cmd"].includes(ext)) {
    return <FileTerminal size={14} />;
  }
  if (["env", "secret", "pem", "crt", "key"].includes(ext)) {
    return <FileKey size={14} />;
  }
  if (["json", "yaml", "yml", "toml", "ini"].includes(ext)) {
    return <Braces size={14} />;
  }
  if (
    [
      "ts",
      "tsx",
      "js",
      "jsx",
      "py",
      "rs",
      "go",
      "java",
      "c",
      "h",
      "cpp",
      "hpp",
      "cs",
      "rb",
      "php",
      "swift",
      "kt",
      "lua",
      "r",
      "vue",
      "svelte",
    ].includes(ext)
  ) {
    return <FileCode size={14} />;
  }
  if (["html", "htm", "xml", "css", "scss", "less"].includes(ext)) {
    return <FileCode size={14} />;
  }
  if (["md", "markdown", "txt", "rtf", "log"].includes(ext)) {
    return <FileText size={14} />;
  }
  return <FileText size={14} />;
}

function TreeNode({
  node,
  repoPath,
  changedFiles,
  selectedPath,
  onSelectFile,
  depth,
  expandTo,
}: TreeNodeProps) {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState<WorkspaceFileNode[] | null>(node.children);
  const [loading, setLoading] = useState(false);
  const expandedByRef = useRef<string | null>(null);

  // 当 expandTo 变化时，如果当前目录是目标路径的前缀，自动展开
  useEffect(() => {
    if (!node.isDir || !expandTo) return;
    // 目标文件在当前目录下（当前目录路径 + "/" 是目标路径的前缀）
    const dirPrefix = node.path ? `${node.path}/` : "";
    if (!expandTo.startsWith(dirPrefix)) return;
    // 已经展开过同一个 expandTo，跳过
    if (expandedByRef.current === expandTo) return;
    expandedByRef.current = expandTo;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 受控展开：外部指定目标文件时同步展开所在目录
    if (!open) setOpen(true);
    if (children === null) {
      const cacheKey = `${repoPath}\u0000${node.path}`;
      const cached = dirCache.get(cacheKey);
      if (cached) {
        setChildren(cached);
      } else {
        setLoading(true);
        void getDirChildren(repoPath, node.path)
          .then((data) => {
            dirCache.set(cacheKey, data);
            setChildren(data);
          })
          .catch(() => setChildren([]))
          .finally(() => setLoading(false));
      }
    }
  }, [expandTo, node.isDir, node.path, repoPath, open, children]);

  const handleClick = async () => {
    if (!node.isDir) {
      onSelectFile(node.path);
      return;
    }
    const next = !open;
    setOpen(next);
    if (next && children === null) {
      const cacheKey = `${repoPath}\u0000${node.path}`;
      const cached = dirCache.get(cacheKey);
      if (cached) {
        setChildren(cached);
        return;
      }
      setLoading(true);
      try {
        const data = await getDirChildren(repoPath, node.path);
        dirCache.set(cacheKey, data);
        setChildren(data);
      } catch {
        setChildren([]);
      } finally {
        setLoading(false);
      }
    }
  };

  const selected = !node.isDir && selectedPath === node.path;
  const changed = !node.isDir && changedFiles.has(node.path);

  return (
    <div className="file-tree-branch">
      <div
        role="button"
        tabIndex={0}
        className={`file-tree-node${selected ? " selected" : ""}`}
        style={{ paddingLeft: 6 + depth * 14 }}
        onClick={() => void handleClick()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            void handleClick();
          }
        }}
        title={node.path}
      >
        {node.isDir ? (
          <ChevronRight size={13} className={`file-tree-chevron${open ? " open" : ""}`} />
        ) : (
          <span className="file-tree-file-indent" />
        )}
        {node.isDir ? (
          open ? (
            <FolderOpen size={14} className="file-tree-folder-icon open" />
          ) : (
            <Folder size={14} className="file-tree-folder-icon" />
          )
        ) : (
          fileIcon(node.name)
        )}
        <span className="file-tree-name">{node.name}</span>
        {loading && <span className="file-tree-loading" />}
        {changed && <span className="file-tree-changed-dot" />}
      </div>
      {open && children && (
        <div className="file-tree-children">
          {children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              repoPath={repoPath}
              changedFiles={changedFiles}
              selectedPath={selectedPath}
              onSelectFile={onSelectFile}
              depth={depth + 1}
              expandTo={expandTo}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function FileTree({
  repoPath,
  changedFiles,
  selectedPath,
  onSelectFile,
  width,
  expandTo,
}: FileTreeProps) {
  const { t } = useTranslation();
  const [nodes, setNodes] = useState<WorkspaceFileNode[] | null>(null);

  useEffect(() => {
    let active = true;
    if (!isTauri()) return;
    const load = () => {
      const cached = treeCache.get(repoPath);
      if (cached) setNodes(cached);
      else setNodes(null);
      void getFileTree(repoPath)
        .then((data) => {
          if (active) {
            treeCache.set(repoPath, data);
            setNodes(data);
          }
        })
        .catch(() => {
          if (active) setNodes([]);
        });
    };
    load();
    let unlisten: (() => void) | undefined;
    void listenWorkspaceChanges((payload) => {
      const changed = normalizePath(payload.path);
      // 忽略 git 元数据与系统文件：hover GitInfoCard 时服务端跑 git status
      // 会刷新 .git/index，触发 workspace:changed 导致文件树被误刷新
      // （收起 → 重新展开到当前文件，页面跳动）
      const segments = changed.split("/");
      if (segments.includes(".git")) return;
      if (changed.endsWith(".DS_Store")) return;
      const root = normalizePath(repoPath);
      if (changed !== root && !changed.startsWith(`${root}/`)) return;
      treeCache.delete(repoPath);
      dirCache.clear();
      load();
    }).then((stop) => {
      if (active) unlisten = stop;
      else stop();
    });
    return () => {
      active = false;
      unlisten?.();
    };
  }, [repoPath]);

  if (!isTauri()) {
    return (
      <div className="file-tree-empty" style={{ width, minWidth: width }}>
        {t("file.desktopTreeOnly", "桌面端支持文件树")}
      </div>
    );
  }
  if (nodes === null) {
    return (
      <div className="file-tree-empty" style={{ width, minWidth: width }}>
        {t("file.loading", "加载中...")}
      </div>
    );
  }
  if (nodes.length === 0) {
    return (
      <div className="file-tree-empty" style={{ width, minWidth: width }}>
        {t("file.emptyDirectory", "空目录")}
      </div>
    );
  }

  return (
    <div className="file-tree" style={{ width, minWidth: width }}>
      {nodes.map((node) => (
        <TreeNode
          key={node.path}
          node={node}
          repoPath={repoPath}
          changedFiles={changedFiles}
          selectedPath={selectedPath}
          onSelectFile={onSelectFile}
          depth={0}
          expandTo={expandTo}
        />
      ))}
    </div>
  );
}
