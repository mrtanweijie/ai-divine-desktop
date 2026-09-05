import {
  BrickWall,
  Bug,
  CalendarDays,
  ChartArea,
  Code,
  DatabaseZap,
  FileSliders,
  Folder,
  Gamepad2,
  GitBranchPlus,
  Mail,
  Wallet,
  type LucideIcon,
} from "lucide-react";

export const PROJECT_ICON_OPTIONS = [
  "folder",
  "file-sliders",
  "brick-wall",
  "mail",
  "calendar-days",
  "wallet",
  "chart-area",
  "database-zap",
  "code",
  "bug",
  "git-branch-plus",
  "gamepad-2",
] as const;

const ICONS: Record<string, LucideIcon> = {
  folder: Folder,
  "file-sliders": FileSliders,
  "brick-wall": BrickWall,
  mail: Mail,
  "calendar-days": CalendarDays,
  wallet: Wallet,
  "chart-area": ChartArea,
  "database-zap": DatabaseZap,
  code: Code,
  bug: Bug,
  "git-branch-plus": GitBranchPlus,
  "gamepad-2": Gamepad2,
};

interface ProjectIconProps {
  icon?: string | null;
  size?: number;
  className?: string;
}

export function ProjectIcon({ icon, size = 13, className }: ProjectIconProps) {
  const Icon = ICONS[icon ?? "folder"] ?? Folder;
  return <Icon size={size} className={className} />;
}
