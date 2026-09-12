import { request } from "./request";

/** 长期记忆条目（对应服务端 user_memories，设计 022） */
export interface MemoryItem {
  id: string;
  category: "preference" | "fact" | "event" | "procedure";
  content: string;
  importance: number;
  confidence: number;
  status: "active" | "pending" | "superseded";
  source_session_id: string | null;
  created_at: string;
  updated_at: string;
  superseded_at: string | null;
  superseded_by: string | null;
  last_accessed_at: string | null;
  project_id: string | null;
}

export interface MemoryListResult {
  memories: MemoryItem[];
  pending_count: number;
}

export type MemoryStatus = "active" | "pending";

export function listMemories(status: MemoryStatus = "active"): Promise<MemoryListResult> {
  return request<MemoryListResult>(`/memories?status=${status}`);
}

export function confirmMemory(id: string): Promise<{ success: boolean }> {
  return request(`/memories/${id}/confirm`, { method: "POST" });
}

export function rejectMemory(id: string): Promise<{ success: boolean }> {
  return request(`/memories/${id}/reject`, { method: "POST" });
}

export function deleteMemory(id: string): Promise<{ success: boolean }> {
  return request(`/memories/${id}`, { method: "DELETE" });
}

/** L3 程序记忆等的人工导入通道（模型侧不可写 procedure） */
export function importMemory(body: {
  content: string;
  category: string;
  importance?: number;
  confidence?: number;
  project_id?: string | null;
}): Promise<{ memory: MemoryItem }> {
  return request("/memories", { method: "POST", body: JSON.stringify(body) });
}
