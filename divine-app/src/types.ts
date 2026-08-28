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
  /** 项目下所有会话累计消耗的 token */
  token_total?: number;
  /** 排序顺序，数值越小越靠前 */
  sort_order?: number;
  /** 是否置顶 */
  pinned?: boolean | number;
}

export interface Session {
  id: string;
  title: string;
  project_id: string | null;
  approval_mode: ApprovalMode;
  locale?: string;
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
  /** 选项卡片的已选状态（{selected, sentCustom}），选择后置灰持久化 */
  choice_state?: Record<string, unknown>;
  /** 本条回复消耗的 token（服务端 token_usage 表 LEFT JOIN 嵌入） */
  token_usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    source: "real" | "estimated";
  };
}

export interface ToolEvent {
  tool: string;
  call_id?: string;
  count?: number;
  urls?: string[];
  files?: ToolFileLink[];
  status: "preparing" | "running" | "confirm" | "done" | "error";
  message: string;
  messageKey?: string;
  messageParams?: Record<string, unknown>;
  currentUrl?: string;
  command?: string;
  commands?: string[];
  confirm_type?:
    | "terminal"
    | "external_file"
    | "plan"
    | "plan_choice"
    | "write_calendar"
    | "skill_migrate"
    | "skill_migrate_batch"
    | "skill_install"
    | "subagents_write";
  skill_migrate?: SkillMigrationCandidate;
  skill_migrations?: SkillMigrationCandidate[];
  skill_install?: SkillInstallPreview;
  subagent_write?: {
    tasks: { id: string; name: string; write_paths?: string[] }[];
  };
  target?: "project" | "user";
  paths?: string[];
  session_id?: string;
  result?: {
    file_name?: string;
    filepath?: string;
    download_url?: string;
    file_size?: number;
    message?: string;
    messageKey?: string;
    messageParams?: Record<string, unknown>;
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

export interface SkillMigrationCandidate {
  name: string;
  source_tool: string;
  kind: "skill_dir" | "cursor_rule";
  source_path: string;
  source_dir?: string;
  description: string;
  preview: string;
  existing: boolean;
  target: "project" | "user";
}

export interface SkillInstallPreview {
  repo: string;
  skills: SkillInstallCandidate[];
}

export interface SkillInstallCandidate {
  name: string;
  skill_path: string;
  description: string;
  preview: string;
  files: string[];
  requirements: string;
  size: number;
}

export interface InstalledSkill {
  name: string;
  description: string;
  type: "knowledge" | "executable" | "mcp";
  source: string;
  version: string;
  path: string;
  dependencies: string[];
  body: string;
  references: string[];
  script_path: string | null;
  script_mode: "cli" | "json";
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

export interface SubAgentItem {
  id: string;
  name: string;
  status: "running" | "done" | "error";
  summary?: string;
  error?: string;
  changed_files?: { path: string; action: string; diff?: string }[];
  changed_count?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  think?: string;
  thinking?: boolean;
  todos?: TodoItem[];
  /** 并行子 Agent 执行状态（可折叠进度面板） */
  subagents?: SubAgentItem[];
  tools: ToolEvent[];
  files?: ChatFile[];
  streaming?: boolean;
  error?: string;
  /** 选项卡片的已选状态（选择后置灰持久化） */
  choice_state?: Record<string, unknown>;
  /** 本条回复消耗的 token（real=API 上报，estimated=本地估算） */
  token_usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    source: "real" | "estimated";
  };
}

export interface ChatFile {
  name: string;
  size?: number;
  content?: string;
  path?: string;
}

export type ModelProvider = "auto" | "langchain" | "mock" | "local";

/** Tool-calling paradigm for a model entry. `auto` resolves to native
 * function calling; `react` uses the ReAct text loop (for endpoints without
 * function-calling support). */
export type ToolMode = "auto" | "native" | "react";

/** A configured model entry as returned by the server (api keys never leave
 * the server; only `has_api_key` is exposed). */
export interface ModelConfig {
  id: string;
  name: string;
  provider: ModelProvider;
  model: string;
  base_url: string;
  has_api_key: boolean;
  active: boolean;
  tool_mode?: ToolMode;
  /** 用户显式选择的提供方 key（deepseek/xiaomi/glm/.../custom）。
   * 持久化后不再依赖模型名前缀反推，避免 qwen2.5:14b 等本地模型被误判。 */
  vendor?: string;
  /** 自定义模型名，逗号分隔；对话切换时合并到该提供方 list 之后（去重） */
  custom_models?: string;
}

/** A model entry as submitted to the server when saving settings. `api_key`
 * is only included when the user typed a new value; empty keeps the stored key. */
export interface ModelConfigPayload {
  id?: string;
  name: string;
  provider: ModelProvider;
  model: string;
  base_url?: string;
  api_key?: string;
  active: boolean;
  tool_mode?: ToolMode;
  vendor?: string;
  custom_models?: string;
}

export type SettingsSaveBody = Partial<Omit<Settings, "models">> & {
  api_key?: string;
  glm_api_key?: string;
  models?: ModelConfigPayload[];
};

export interface Settings {
  provider: string;
  base_url: string;
  model: string;
  has_api_key: boolean;
  has_glm_key: boolean;
  workspace_dir: string;
  username: string;
  think_default: boolean;
  reasoning_effort: string;
  context_limit: number;
  tools: ToolDefinition[];
  models: ModelConfig[];
  // 本地模型配置
  local_llm_enabled: boolean;
  local_llm_mode: "keyword" | "local" | "hybrid";
  local_llm_port: number;
  local_llm_model: string;
  local_llm_ctx_size: number;
  local_llm_threshold: number;
  installed_models: InstalledModel[];
}

export interface ToolDefinition {
  name: string;
  description: string;
  category: string;
  parameters: Record<string, unknown>;
}

export interface InstalledModel {
  id: string;
  name: string;
  path: string;
  size: number;
  enabled: boolean;
}

export interface RecommendedModel {
  id: string;
  name: string;
  description: string;
  size_gb: number;
  required_ram_gb: number;
  quantization: string;
  recommended: boolean;
  tags: string[];
  installed: boolean;
  incomplete?: boolean;
}

export interface HardwareInfo {
  ram_total_gb: number;
  ram_available_gb: number;
  cpu_cores: number;
  has_gpu: boolean;
  gpu_name: string;
  gpu_memory_gb: number;
  platform: string;
  arch: string;
}

export interface DownloadProgress {
  downloaded: number;
  total: number;
  percent: number;
}

export interface LocalLLMStatus {
  enabled: boolean;
  mode: "keyword" | "local" | "hybrid";
  llama_server_running: boolean;
  port: number;
  threshold: number;
  hardware: HardwareInfo;
  installed_models: InstalledModel[];
  recommended_models: RecommendedModel[];
  custom_models: RecommendedModel[];
  active_model: string | null;
  download_progress: Record<string, DownloadProgress>;
  // backend 附加字段
  running: boolean;
  binary: string | null;
  pid: number | null;
  last_error: string | null;
  llama_server_installed: boolean;
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

/** Token usage breakdown for the composer context ring. */
export interface ContextUsage {
  usedPercent: number;
  estimatedTokens: number;
  contextWindow: number;
  compactable: boolean;
  hasSummary: boolean;
  breakdown: {
    systemPrompt: number;
    tools: number;
    messages: number;
  };
}

export interface CompactResult {
  ok: boolean;
  compacted: boolean;
  message?: string;
  summary?: string;
  savedTokens?: number;
  usage: ContextUsage;
}

export interface PreviewFile {
  repoPath: string;
  relPath: string;
  fileName?: string;
  path?: string;
  content?: string;
}
