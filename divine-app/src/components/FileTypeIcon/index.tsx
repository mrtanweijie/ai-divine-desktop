import {
  BookMarked,
  Braces,
  Database,
  FileArchive,
  FileCode,
  FileCog,
  FileImage,
  FileKey,
  FileMusic,
  FileSpreadsheet,
  FileStack,
  FileTerminal,
  FileText,
  FileVideoCamera,
  Presentation,
  type LucideIcon,
} from "lucide-react";
import { fileIconKind, type FileIconKind } from "./kinds";

export type { FileIconKind } from "./kinds";

/** 图标类型 → 图标（判定逻辑见 `./kinds.ts`，此处只管长相）。 */
const KIND_ICONS: Record<FileIconKind, LucideIcon> = {
  build: FileCog,
  image: FileImage,
  archive: FileArchive,
  audio: FileMusic,
  video: FileVideoCamera,
  sheet: FileSpreadsheet,
  slides: Presentation,
  word: BookMarked,
  pdf: FileStack,
  database: Database,
  terminal: FileTerminal,
  key: FileKey,
  config: Braces,
  code: FileCode,
  doc: FileText,
};

interface FileTypeIconProps {
  /** 文件名或路径（带目录时按 basename 判断后缀） */
  name: string;
  size?: number;
  className?: string;
}

/**
 * 按文件后缀显示对应图标。全应用共用：文件树 / `@` 候选浮层 / 气泡内 `@文件` 引用 /
 * 附件 chip / 工具产物文件列表——同一个文件在任何位置长相必须一致。
 *
 * 目录不在此列：文件树由 `node.isDir` 分支处理，无后缀/未知后缀一律落文档图标。
 */
export function FileTypeIcon({ name, size = 14, className }: FileTypeIconProps) {
  const Icon = KIND_ICONS[fileIconKind(name)];
  return <Icon size={size} className={className} />;
}
