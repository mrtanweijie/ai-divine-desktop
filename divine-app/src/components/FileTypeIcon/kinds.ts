/**
 * 文件名 → 图标类型（纯函数，无 React 依赖，便于直接跑验证）。
 *
 * **唯一真源**：文件树、`@` 候选浮层、气泡内引用/附件 chip、工具产物文件列表
 * 全部经此判定。2026-09-14 之前仓里并存两份映射（FileTree 一份、MessageHelpers
 * 一份，且互有缺失——pdf 只在后者有），此处合并为并集。
 */
export type FileIconKind =
  | "build"
  | "image"
  | "archive"
  | "audio"
  | "video"
  | "sheet"
  | "slides"
  | "word"
  | "pdf"
  | "database"
  | "terminal"
  | "key"
  | "config"
  | "code"
  | "doc";

/** 顺序即优先级：先命中先返回（`.key` 归 slides 而非证书，就靠这个顺序）。 */
const EXT_GROUPS: { kind: FileIconKind; ext: string[] }[] = [
  { kind: "image", ext: ["png", "jpg", "jpeg", "gif", "webp", "svg", "ico", "avif"] },
  { kind: "archive", ext: ["zip", "tar", "gz", "7z", "rar", "xz", "bz2"] },
  { kind: "audio", ext: ["mp3", "wav", "flac", "aac", "ogg", "m4a"] },
  { kind: "video", ext: ["mp4", "mov", "avi", "mkv", "webm", "flv"] },
  { kind: "sheet", ext: ["xlsx", "xls", "csv", "tsv", "numbers"] },
  // Keynote 的 `.key` 走这里；证书类 `.key` 的规则在其后，永远命中不到——历史顺序，勿调
  { kind: "slides", ext: ["ppt", "pptx", "key"] },
  { kind: "word", ext: ["doc", "docx", "odt", "pages"] },
  { kind: "pdf", ext: ["pdf"] },
  { kind: "database", ext: ["db", "sqlite", "sqlite3", "sql"] },
  { kind: "terminal", ext: ["sh", "bash", "zsh", "ps1", "bat", "cmd"] },
  { kind: "key", ext: ["env", "secret", "pem", "crt"] },
  { kind: "config", ext: ["json", "yaml", "yml", "toml", "ini"] },
  {
    kind: "code",
    ext: [
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
      "html",
      "htm",
      "xml",
      "css",
      "scss",
      "less",
    ],
  },
];

/** 无后缀但一眼能认的工程文件名。 */
const BUILD_NAMES = ["dockerfile", "makefile"];

/** 取 basename 的小写形式：引用可能是完整相对路径（`assets/a.jpg`）。 */
function baseName(name: string): string {
  return (name.replace(/\\/g, "/").split("/").pop() ?? name).toLowerCase();
}

export function fileIconKind(name: string): FileIconKind {
  const base = baseName(name);
  if (!base) return "doc";
  if (BUILD_NAMES.includes(base)) return "build";
  // `.env` 取 `env`（点号在首位也算后缀），与历史逻辑同口径
  const ext = base.includes(".") ? (base.split(".").pop() ?? "") : "";
  return EXT_GROUPS.find((group) => group.ext.includes(ext))?.kind ?? "doc";
}
