export interface Session {
  id: string;
  title: string;
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
}

export interface ToolEvent {
  tool: string;
  status: "preparing" | "running" | "confirm" | "done" | "error";
  message: string;
  command?: string;
  confirm_type?: "terminal" | "external_file";
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
  };
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

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  think?: string;
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

export interface WorkspaceFile {
  name: string;
  size: number;
  download_url: string;
}

export interface WorkspaceCategory {
  category: string;
  files: WorkspaceFile[];
}
