export { downloadUrl, getWorkspace } from "@/services/api";

export function toWorkspaceRelative(
  base: string,
  filePath: string
): string | null {
  const baseNorm = base.replace(/\\/g, "/").replace(/\/+$/, "");
  const fileNorm = filePath.replace(/\\/g, "/");
  if (fileNorm === baseNorm) return null;
  if (fileNorm.startsWith(`${baseNorm}/`)) {
    return fileNorm.slice(baseNorm.length + 1);
  }
  return null;
}

export function workspaceJoin(base: string, relPath: string): string {
  return `${base.replace(/\\/g, "/").replace(/\/+$/, "")}/${relPath.replace(
    /^\/+/,
    ""
  )}`;
}
