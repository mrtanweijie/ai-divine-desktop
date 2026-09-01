// Tool icon mapping: tool name -> lucide icon.
import {
  Activity,
  BarChart3,
  Blend,
  BookAudio,
  BookMarked,
  BookOpenCheck,
  BookSearch,
  Box,
  Brain,
  Calculator,
  CalendarClock,
  CalendarDays,
  CircleStop,
  Copy,
  Database,
  FileBox,
  FileCode2,
  FileDiff,
  FilePlus2,
  FileSpreadsheet,
  FileText,
  FlaskConical,
  FolderInput,
  FolderSearch2,
  FolderTree,
  GitBranch,
  GitBranchMinus,
  GitCommit,
  GitCommitHorizontal,
  GitCompareArrows,
  GitGraph,
  Globe,
  Group,
  Image,
  ImageDown,
  LibraryBig,
  ListOrdered,
  ListTree,
  Orbit,
  Package,
  Paintbrush,
  PenTool,
  Presentation,
  Regex,
  ScanSearch,
  ScrollText,
  SquareKanban,
  StickyNote,
  TerminalSquare,
  Workflow,
} from "lucide-react";

export function toolIcon(tool: string) {
  if (tool === "edit_files") return <Group size={16} />;
  if (tool === "write_file") return <FilePlus2 size={16} />;
  if (tool === "edit_lines") return <ListOrdered size={16} />;
  if (tool === "apply_patch") return <FileDiff size={16} />;
  if (tool === "move_file") return <FolderInput size={16} />;
  if (tool === "glob_files") return <Regex size={16} />;
  if (tool === "list_definitions") return <ListTree size={16} />;
  if (tool === "lint_check") return <ScanSearch size={16} />;
  if (tool === "run_tests") return <FlaskConical size={16} />;
  if (tool === "format_code") return <Paintbrush size={16} />;
  if (tool.startsWith("bg_")) {
    if (tool === "bg_kill") return <CircleStop size={16} />;
    if (tool === "bg_output") return <ScrollText size={16} />;
    return <Activity size={16} />;
  }
  if (tool.includes("memory")) return <Brain size={16} />;
  if (tool === "run_subagents") return <GitGraph size={16} />;
  if (tool === "git_status") return <GitBranch size={16} />;
  if (tool === "git_diff") return <GitCompareArrows size={16} />;
  if (tool === "git_log") return <GitCommitHorizontal size={16} />;
  if (tool === "git_commit") return <GitCommit size={16} />;
  if (tool === "git_revert") return <GitBranchMinus size={16} />;
  if (tool === "draw_svg") return <FileBox size={16} />;
  if (tool === "describe_svg" || tool === "edit_svg") return <Orbit size={16} />;
  if (tool.includes("svg_to_png")) return <ImageDown size={16} />;
  if (tool.includes("svg")) return <PenTool size={16} />;
  if (tool === "schedule_task") return <CalendarClock size={16} />;
  if (tool === "write_calendar") return <CalendarDays size={16} />;
  if (tool.includes("spreadsheet") || tool.includes("excel"))
    return <FileSpreadsheet size={16} />;
  if (tool.includes("notes")) return <StickyNote size={16} />;
  if (tool === "read_file") return <BookMarked size={16} />;
  if (tool.includes("read_image") || tool.includes("image"))
    return <Image size={16} />;
  if (tool.includes("calculator")) return <Calculator size={16} />;
  if (tool.includes("clipboard")) return <Copy size={16} />;
  if (tool.includes("sqlite") || tool.includes("database"))
    return <Database size={16} />;
  if (tool.includes("rag_index")) return <LibraryBig size={16} />;
  if (tool.includes("rag_search")) return <BookSearch size={16} />;
  if (tool.includes("grep")) return <BookOpenCheck size={16} />;
  if (tool === "web_search") return <Blend size={16} />;
  if (tool.includes("search_files") || tool.includes("search"))
    return <FolderSearch2 size={16} />;
  if (tool === "create_plan") return <SquareKanban size={16} />;
  if (tool.includes("pdf")) return <BookAudio size={16} />;
  if (tool.includes("directory") || tool.includes("tree"))
    return <FolderTree size={16} />;
  if (tool === "generate_chart" || tool.includes("chart"))
    return <BarChart3 size={16} />;
  if (tool.includes("mermaid") || tool.includes("diagram"))
    return <Workflow size={16} />;
  if (
    tool.includes("requirements") ||
    tool.includes("html") ||
    tool.includes("prd") ||
    tool.includes("ux")
  )
    return <FileCode2 size={16} />;
  if (
    tool.includes("presentation") ||
    tool.includes("ppt") ||
    tool.includes("slides")
  )
    return <Presentation size={16} />;
  if (tool === "web_fetch_batch") return <Package size={16} />;
  if (tool === "web_fetch") return <Box size={16} />;
  if (
    tool.includes("web") ||
    tool.includes("fetch") ||
    tool.includes("browse") ||
    tool.includes("url")
  )
    return <Globe size={16} />;
  if (tool === "terminal") return <TerminalSquare size={16} />;
  return <FileText size={16} />;
}
