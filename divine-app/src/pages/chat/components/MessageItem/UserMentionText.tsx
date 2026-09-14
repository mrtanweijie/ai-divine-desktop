import { Sparkles } from "lucide-react";
import { memo } from "react";
import { useTranslation } from "react-i18next";
import { FileTypeIcon } from "@/components/FileTypeIcon";
import { parseMentionSegments } from "@/pages/chat/chatUtils";
import type { PreviewFile } from "@/types";

interface UserMentionTextProps {
  text: string;
  /** 会话生效工作区根目录（绝对路径），用于把相对路径解析成可预览文件 */
  workspacePath?: string | null;
  /** 当前会话可用技能名集合（已规范化）；未就绪时传 undefined，退回纯词法判断 */
  knownSkills?: ReadonlySet<string>;
  onPreviewFile?: (file: PreviewFile) => void;
}

/**
 * 用户气泡正文渲染：`@路径` 渲染为可点击链接（打开右侧 FilePreviewModal），
 * `/技能名` 渲染为等宽胶囊。两类 token 形状与颜色不同——一眼区分"作用对象"与"做事方法"。
 *
 * 技能胶囊只对**真实存在的技能**渲染（`knownSkills` 命中），`见 /docs 目录` 这类
 * 路径写法还原为普通文本；胶囊内显示不带 `/` 前缀的技能名，前缀已由图标 + 等宽字形表达。
 *
 * 纯展示层：不改动 message.content，复制按钮与后端落库仍是原始文本
 * （见 docs/design/025-chat-mention-files-20260913.md §1.4 / §2.2）。
 */
export const UserMentionText = memo(function UserMentionText({
  text,
  workspacePath,
  knownSkills,
  onPreviewFile,
}: UserMentionTextProps) {
  const { t } = useTranslation();
  const segments = parseMentionSegments(text, knownSkills);

  return (
    <>
      {segments.map((segment, index) => {
        if (segment.type === "skill") {
          return (
            <span
              className="user-mention user-mention-skill"
              key={`skill-${index}`}
              title={t("chat.mentionSkillTitle", "技能引用：{{name}}", { name: segment.name })}
            >
              <Sparkles size={11} />
              {segment.name}
            </span>
          );
        }
        if (segment.type === "file") {
          const filePath = segment.path;
          const canPreview = Boolean(onPreviewFile);
          const openPreview = () =>
            onPreviewFile?.({
              repoPath: workspacePath ?? "",
              relPath: filePath,
              fileName: filePath.split("/").pop(),
            });
          return (
            <span
              className={`user-mention user-mention-file${
                canPreview ? " user-mention-file--link" : ""
              }`}
              key={`file-${index}`}
              role={canPreview ? "button" : undefined}
              tabIndex={canPreview ? 0 : undefined}
              title={canPreview ? `${t("chat.preview", "预览")} ${filePath}` : filePath}
              onClick={canPreview ? openPreview : undefined}
              onKeyDown={
                canPreview
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        openPreview();
                      }
                    }
                  : undefined
              }
            >
              <FileTypeIcon name={filePath} size={11} />
              {filePath}
            </span>
          );
        }
        return <span key={`text-${index}`}>{segment.text}</span>;
      })}
    </>
  );
});
