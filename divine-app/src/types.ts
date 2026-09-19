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
  last_message?: string;
}

export interface MessagePart {
  id: string;
  message_id: string;
  type: "think" | "tool" | "file" | "tool_calls" | "tool_result" | "preprocess";
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
  /** 消息来源：normal=云端/local=本地模型/local_fallback=本地拒答转云端 */
  source?: string;
  /** 本条回复消耗的 token（服务端 token_usage 表 LEFT JOIN 嵌入） */
  token_usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    source: "real" | "estimated";
    created_at?: string;
    duration_ms?: number | null;
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
    | "git"
    | "external_file"
    | "plan"
    | "plan_choice"
    | "write_calendar"
    | "skill_migrate"
    | "skill_migrate_batch"
    | "skill_install"
    | "subagents_write"
    | "preprocess_fallback"
    | "ask_user";
  /** ask_user 问题（confirm_type=ask_user 时） */
  question?: string;
  /** ask_user 候选选项 */
  options?: string[];
  /** ask_user 输入类型 */
  input_type?: "text" | "single_choice" | "multi_choice";
  skill_migrate?: SkillMigrationCandidate;
  skill_migrations?: SkillMigrationCandidate[];
  skill_install?: SkillInstallPreview;
  subagent_write?: {
    tasks: { id: string; name: string; write_paths?: string[] }[];
  };
  target?: "project" | "user";
  paths?: string[];
  session_id?: string;
  /** 模型调用轮次（ReAct 第几轮），TurnCounterMiddleware 维护 */
  turn?: number;
  /** 合并卡的起始轮次（重试链/白名单组的第一条） */
  turn_start?: number;
  /** 合并卡内失败次数（重试链聚合） */
  failed_count?: number;
  /** tool_runs.id，done/error 时携带 */
  run_id?: string;
  /** 工具开始时间（ISO8601），done/error 时携带 */
  started_at?: string;
  /** 工具耗时（毫秒），done/error 时携带 */
  duration_ms?: number;
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
  /** 模型调用轮次（新数据才有；旧库行为 NULL） */
  turn?: number | null;
  /** 工具耗时毫秒（新数据才有；旧库行为 NULL） */
  duration_ms?: number | null;
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
  /** 本地预整理：长文本被整理成结构化版本，原文可展开查看 */
  preprocess?: ChatPreprocess;
  /** 发送后等待本地预整理（冷启动/分块）期间显示"正在本地整理"提示 */
  preprocess_pending?: boolean;
  streaming?: boolean;
  error?: string;
  /** 本轮 `/技能` 引用中未被真正使用的技能名（后端 done 事件回传，仅作提示） */
  unused_mentions?: string[];
  /** 选项卡片的已选状态（选择后置灰持久化） */
  choice_state?: Record<string, unknown>;
  /** 消息来源：normal=云端/local=本地模型/local_fallback=本地拒答转云端 */
  source?: string;
  /** 本条回复消耗的 token（real=API 上报，estimated=本地估算） */
  token_usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    source: "real" | "estimated";
    created_at?: string;
    duration_ms?: number | null;
  };
}

export interface ChatFile {
  name: string;
  size?: number;
  content?: string;
  path?: string;
}

/** `@文件` / `/技能` 两种引用类型。 */
export type MentionKind = "file" | "skill";

/** 发送时提交的结构化引用（后端只信这个数组，不从消息正文反向抽取）。 */
export interface MentionRef {
  type: MentionKind;
  /** 文件为工作区相对路径 */
  path?: string;
  /** 技能为名称 */
  name?: string;
}

/** 技能分类：knowledge=知识技能（方法论/SOP），executable/mcp=能力技能（可执行）。 */
export type SkillCandidateType = "knowledge" | "executable" | "mcp";

/** 技能来源：项目级 / 用户级 / 内置。 */
export type SkillCandidateSource = "project" | "user" | "builtin";

/** `@` / `/` 候选条目（GET /api/workspace/mentions 的 items 元素）。 */
export interface MentionCandidate {
  kind: MentionKind;
  /** 插入文本：文件为工作区相对路径，技能为技能名 */
  path: string;
  type?: "file" | "dir" | SkillCandidateType;
  size?: number;
  mtime?: number;
  /** 技能候选：名称（与 path 同值，保留独立字段以便后续消歧串处理） */
  name?: string;
  /** 技能候选：来源 */
  source?: SkillCandidateSource;
  /** 技能候选：描述（弹层内截断展示） */
  description?: string;
  version?: string;
}

/** 本地预整理标记（message part type="preprocess"）。
 * 长文本被本地模型整理成结构化版本后，原文存于 original 供前端展开查看；
 * original_path 是工作区里的原文附件路径（云端 read_file 按需读取）。 */
export interface ChatPreprocess {
  organized: boolean;
  original_path?: string;
  original?: string;
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

/** MCP 外部服务器配置（env 密钥：后端只回空串占位，回传空串=保留已存值） */
export interface McpServerConfig {
  id: string;
  name: string;
  transport: "stdio" | "http";
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  enabled: boolean;
  /** true 时跳过执行前逐次确认 */
  trusted?: boolean;
}

/** MCP server 实时状态（/api/mcp/servers 返回） */
export interface McpServerStatus {
  id: string;
  name?: string;
  status: "connected" | "error" | "disabled";
  error?: string;
  tools?: { name: string; description: string; inputSchema?: unknown }[];
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
  reasoning_effort: string;
  context_limit: number;
  // 桌面全局快捷键（唤起/隐藏主窗口）
  global_shortcut_enabled: boolean;
  tools: ToolDefinition[];
  models: ModelConfig[];
  // MCP 外部服务器
  mcp_servers?: McpServerConfig[];
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

/** 任务类型：reminder/agent/monitor 为原有，webhook/interactive/digest 见 design 027。 */
export type ScheduledTaskType =
  "reminder" | "agent" | "monitor" | "webhook" | "interactive" | "digest";

/** 一条投递通道配置（飞书 / 企业微信 群机器人）。 */
export interface DeliveryChannel {
  type: "feishu" | "wecom";
  webhook_url: string;
  /** 飞书自定义机器人签名密钥，可选 */
  sign_secret?: string;
  /** 企业微信 @ 的手机号，可选 */
  at_mobiles?: string[];
}

export interface DeliveryConfig {
  channels: DeliveryChannel[];
}

/** 一次执行的结果（design 027 §2.2）。只有新三类任务会写。 */
export type TaskRunStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";

export interface TaskRunDelivery {
  ok: boolean;
  status_code?: number | null;
  error?: string | null;
}

export interface TaskRun {
  id: string;
  task_id: string;
  started_at: string;
  finished_at: string | null;
  status: TaskRunStatus;
  output: string;
  error: string;
  /** channel 名 → 投递结果，例如 { feishu: { ok: true } } */
  delivery_status: Record<string, TaskRunDelivery>;
}

/** 交互任务配置（design 027 §3.4）：询问卡片文案与过期时间。 */
export interface InteractiveConfig {
  notification_title?: string;
  notification_body?: string;
  action_label?: string;
  reject_label?: string;
  /** 等待用户决策的秒数，默认 600 */
  expire_seconds?: number;
}

/** 每日摘要配置：来源列表。摘要 prompt 模板复用 `ScheduledTask.prompt`。 */
export interface DigestConfig {
  sources: string[];
}

export interface ScheduledTask {
  id: string;
  session_id: string | null;
  title: string;
  description: string;
  task_type: ScheduledTaskType;
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
  // --- design 027：执行内容 / 投递 / 交互 ---
  /** 任务提示词；webhook/interactive/digest 用它作为 Agent 输入 */
  prompt?: string;
  model_id?: string | null;
  allow_full_access?: boolean;
  /** 后端列名 delivery_json，API 层用 delivery 收发 */
  delivery?: DeliveryConfig;
  delivery_json?: DeliveryConfig;
  interactive?: InteractiveConfig;
  interactive_json?: InteractiveConfig;
  /** 后端列名 digest_json，API 层用 digest 收发 */
  digest?: DigestConfig;
  digest_json?: DigestConfig;
  /** 有值 = 该任务正在等用户决策（票据） */
  pending_user_action?: string | null;
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
