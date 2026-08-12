export type ApprovalMode = "ask" | "assist" | "full";

export interface Project {
  id: string;
  name: string;
  path: string;
  icon: string;
  created_at: string;
  updated_at: string;
  session_count?: number;
  last_activity?: string | null;
}

export interface Session {
  id: string;
  title: string;
  project_id: string | null;
  approval_mode: ApprovalMode;
  created_at: string;
  updated_at: string;
}

export interface MessagePart {
  id: string;
  message_id: string;
  type: "think" | "tool" | "file" | "tool_calls" | "tool_result";
  content: string;
  order: number;
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  created_at: string;
  parts: MessagePart[];
  todos?: TodoItem[];
}

export interface ToolEvent {
  tool: string;
  call_id?: string;
  count?: number;
  urls?: string[];
  files?: ToolFileLink[];
  status: "preparing" | "running" | "confirm" | "done" | "error";
  message: string;
  command?: string;
  confirm_type?:
    | "terminal"
    | "external_file"
    | "plan"
    | "plan_choice"
    | "write_calendar";
  paths?: string[];
  session_id?: string;
  result?: {
    file_name?: string;
    filepath?: string;
    download_url?: string;
    file_size?: number;
    message?: string;
    success?: boolean;
    stdout?: string;
    stderr?: string;
    exit_code?: number;
    data?: {
      title?: string;
      chart_type?: string;
      option?: Record<string, unknown>;
      [key: string]: unknown;
    };
    option?: Record<string, unknown>;
  };
}

export interface ToolFileLink {
  name: string;
  path?: string;
  download_url?: string;
  size?: number;
}

export interface ToolRun {
  id: string;
  session_id: string;
  tool_name: string;
  status: string;
  input: string;
  output: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface TodoItem {
  id: string;
  index: number;
  title: string;
  status: "pending" | "running" | "done" | "error" | "skipped";
  result?: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  think?: string;
  todos?: TodoItem[];
  tools: ToolEvent[];
  files?: ChatFile[];
  streaming?: boolean;
  error?: string;
}

export interface ChatFile {
  name: string;
  size?: number;
  content?: string;
  path?: string;
}

export interface Settings {
  provider: string;
  base_url: string;
  model: string;
  has_api_key: boolean;
  has_glm_key: boolean;
  workspace_dir: string;
  username: string;
  think_default: boolean;
  context_limit: number;
  tools: ToolDefinition[];
}

export interface ToolDefinition {
  name: string;
  description: string;
  category: string;
  parameters: Record<string, unknown>;
}

export interface ScheduledTask {
  id: string;
  session_id: string | null;
  title: string;
  description: string;
  task_type: "reminder" | "agent" | "monitor";
  frequency: "once" | "interval" | "daily" | "weekly" | "monthly";
  interval_minutes: number | null;
  run_at: string | null;
  run_hour: number | null;
  run_minute: number | null;
  days_of_week: number[];
  day_of_month: number | null;
  next_run_at: string | null;
  last_run_at: string | null;
  status: "active" | "paused" | "done";
  calendar_synced: number;
  created_at: string;
  updated_at: string;
}

export interface CalendarEvent {
  id: string;
  title: string;
  start_at: string;
  end_at: string | null;
  notes: string;
  location: string;
  task_id: string | null;
  system_event_id: string | null;
  synced: number;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceFile {
  name: string;
  size: number;
  download_url: string;
}

export interface WorkspaceCategory {
  category: string;
  files: WorkspaceFile[];
}

export interface WorkspaceFileNode {
  name: string;
  path: string;
  isDir: boolean;
  children: WorkspaceFileNode[] | null;
}

export interface FileDiff {
  relPath: string;
  oldContent: string;
  newContent: string;
  diffText: string;
  additions: number;
  deletions: number;
  isGit: boolean;
  tracked: boolean;
  isBinary: boolean;
  exists: boolean;
  contentTruncated: boolean;
}

export interface PreviewFile {
  repoPath: string;
  relPath: string;
  fileName?: string;
}
