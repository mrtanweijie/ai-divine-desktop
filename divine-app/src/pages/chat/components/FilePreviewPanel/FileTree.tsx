import { useEffect, useState } from "react";
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
import { getDirChildren, getFileTree, isTauri } from "@/services/tauri";
import type { WorkspaceFileNode } from "@/types";

interface FileTreeProps {
  repoPath: string;
  changedFiles: ReadonlySet<string>;
  selectedPath: string | null;
  onSelectFile: (relPath: string) => void;
  width: number;
}

interface TreeNodeProps {
  node: WorkspaceFileNode;
  repoPath: string;
  changedFiles: ReadonlySet<string>;
  selectedPath: string | null;
  onSelectFile: (relPath: string) => void;
  depth: number;
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
    return FileCog;
  }
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "ico", "avif"].includes(ext)) {
    return FileImage;
  }
  if (["zip", "tar", "gz", "7z", "rar", "xz", "bz2"].includes(ext)) {
    return FileArchive;
  }
  if (["mp3", "wav", "flac", "aac", "ogg", "m4a"].includes(ext)) {
    return FileMusic;
  }
  if (["mp4", "mov", "avi", "mkv", "webm", "flv"].includes(ext)) {
    return FileVideoCamera;
  }
  if (["xlsx", "xls", "csv", "tsv"].includes(ext)) {
    return FileSpreadsheet;
  }
  if (["ppt", "pptx", "key"].includes(ext)) {
    return Presentation;
  }
  if (["db", "sqlite", "sqlite3", "sql"].includes(ext)) {
    return Database;
  }
  if (["sh", "bash", "zsh", "ps1", "bat", "cmd"].includes(ext)) {
    return FileTerminal;
  }
  if (["env", "secret", "pem", "crt", "key"].includes(ext)) {
    return FileKey;
  }
  if (["json", "yaml", "yml", "toml", "ini"].includes(ext)) {
    return Braces;
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
    return FileCode;
  }
  if (["html", "htm", "xml", "css", "scss", "less"].includes(ext)) {
    return FileCode;
  }
  if (["md", "markdown", "txt", "rtf", "log"].includes(ext)) {
    return FileText;
  }
  return FileText;
}

function TreeNode({
  node,
  repoPath,
  changedFiles,
  selectedPath,
  onSelectFile,
  depth,
}: TreeNodeProps) {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState<WorkspaceFileNode[] | null>(
    node.children
  );
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    if (!node.isDir) {
      onSelectFile(node.path);
      return;
    }
    const next = !open;
    setOpen(next);
    if (next && children === null) {
      setLoading(true);
      try {
        setChildren(await getDirChildren(repoPath, node.path));
      } catch {
        setChildren([]);
      } finally {
        setLoading(false);
      }
    }
  };

  const selected = !node.isDir && selectedPath === node.path;
  const changed = !node.isDir && changedFiles.has(node.path);
  const Icon = node.isDir ? Folder : fileIcon(node.name);

  return (
    <div className="file-tree-branch">
      <button
        type="button"
        className={`file-tree-node${selected ? " selected" : ""}`}
        style={{ paddingLeft: 6 + depth * 14 }}
        onClick={() => void handleClick()}
        title={node.path}
      >
        {node.isDir ? (
          <ChevronRight
            size={13}
            className={`file-tree-chevron${open ? " open" : ""}`}
          />
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
          <Icon size={14} className="file-tree-file-icon" />
        )}
        <span className="file-tree-name">{node.name}</span>
        {loading && <span className="file-tree-loading" />}
        {changed && <span className="file-tree-changed-dot" />}
      </button>
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
}: FileTreeProps) {
  const [nodes, setNodes] = useState<WorkspaceFileNode[] | null>(null);

  useEffect(() => {
    let active = true;
    setNodes(null);
    if (!isTauri()) return;
    void getFileTree(repoPath)
      .then((data) => {
        if (active) setNodes(data);
      })
      .catch(() => {
        if (active) setNodes([]);
      });
    return () => {
      active = false;
    };
  }, [repoPath]);

  if (!isTauri()) {
    return (
      <div className="file-tree-empty" style={{ width, minWidth: width }}>
        桌面端支持文件树
      </div>
    );
  }
  if (nodes === null) {
    return (
      <div className="file-tree-empty" style={{ width, minWidth: width }}>
        加载中...
      </div>
    );
  }
  if (nodes.length === 0) {
    return (
      <div className="file-tree-empty" style={{ width, minWidth: width }}>
        空目录
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
        />
      ))}
    </div>
  );
}
