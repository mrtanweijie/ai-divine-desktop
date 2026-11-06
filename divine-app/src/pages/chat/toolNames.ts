/**
 * 产物以「图片卡片墙」呈现的工具。
 *
 * 这四处判断必须同源（2026-11-05）：
 * 1. `ToolStatusCard` 的卡片墙判定；
 * 2. `ToolStatusCard` 的「已生成」结果行抑制；
 * 3. `useChatStream` 的实时文件回填；
 * 4. `api.ts` 的历史回放文件回填。
 *
 * 此前四处各自写死 `"image_generate"`，新增海报工具时必然漏一处——漏了的表现是
 * 「工具跑完只有一行文件名，没有图」。加新的出图工具时只改这里。
 */
import { changedFilePathsFromResult } from "@/pages/chat/chatUtils";

export const IMAGE_RESULT_TOOLS: ReadonlySet<string> = new Set([
  "image_generate",
  "poster_generate",
]);

export function isImageResultTool(name: string | null | undefined): boolean {
  return typeof name === "string" && IMAGE_RESULT_TOOLS.has(name);
}

/**
 * 取一个图像工具的产物文件列表。
 *
 * **不依赖 `tool.files`**：那是前端在收到 done 事件时补的字段，任何一次工具对象
 * 重建（服务端消息覆盖本地、settle、合并）都可能把它抹掉，表现就是「图生成了但
 * 卡片墙不出现」（2026-11-06 用户实测）。工具结果里本来就有 `filepath` / `data.files`，
 * 这里直接兜住，事件补的 files 只作为更快的路径。
 */
export function imageFilesOf(tool: {
  files?: Array<{ name?: string; path?: string }>;
  result?: unknown;
}): Array<{ name: string; path: string }> {
  const fromEvent = (tool.files ?? [])
    .filter((file): file is { name?: string; path: string } => Boolean(file?.path))
    .map((file) => ({
      name: file.name ?? file.path.split("/").pop() ?? file.path,
      path: file.path,
    }));
  if (fromEvent.length > 0) return fromEvent;

  return changedFilePathsFromResult(tool.result).map((path) => ({
    name: path.split("/").pop() ?? path,
    path,
  }));
}
