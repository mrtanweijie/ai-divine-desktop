import type { ReactNode } from "react";
import {
  FolderSearch,
  Ghost,
  PackageSearch,
  Cherry,
} from "lucide-react";
import avatarUrl from "@/assets/divine-ai-avatar-guide.svg";
import { openFolder } from "@/services/tauri";
import "./index.less";

interface GuideCard {
  key: string;
  icon: ReactNode;
  tone: "blue" | "purple" | "green" | "orange";
  title: string;
  prompt: string;
}

interface NewChatGuideProps {
  projectName: string | null;
  projectPath?: string | null;
  disabled?: boolean;
  onAction: (prompt: string) => void;
}

const CARDS: GuideCard[] = [
  {
    key: "workspace",
    icon: <FolderSearch size={20} />,
    tone: "blue",
    title: "工作空间目录",
    prompt:
      "请查看当前项目工作空间目录，并介绍里面的内容和结构。",
  },
  {
    key: "architecture",
    icon: <Ghost size={20} />,
    tone: "purple",
    title: "分析项目架构",
    prompt:
      "请分析当前项目的工作空间目录结构、技术架构和关键文件，并给出总结。",
  },
  {
    key: "build",
    icon: <Cherry size={20} />,
    tone: "green",
    title: "开始构建新项目",
    prompt:
      "请基于当前项目目录开始构建一个新项目，先制定方案和计划，再逐步实现。",
  },
  {
    key: "fix",
    icon: <PackageSearch size={20} />,
    tone: "orange",
    title: "修复项目问题",
    prompt:
      "请检查当前项目目录中的问题，定位错误并给出修复方案，然后执行修复。",
  },
];

export function NewChatGuide({
  projectName,
  projectPath,
  disabled = false,
  onAction,
}: NewChatGuideProps) {
  return (
    <div className="new-chat-guide">
      <div className="new-chat-guide-icon">
        <img src={avatarUrl} alt="" className="new-chat-guide-avatar-img" />
      </div>
      <h2 className="new-chat-guide-title">
        {projectName ? (
          <>
            要在{" "}
            <span
              className="new-chat-guide-project-link"
              role="button"
              tabIndex={0}
              title={projectPath ?? undefined}
              onClick={(event) => {
                event.stopPropagation();
                if (projectPath) void openFolder(projectPath);
              }}
              onKeyDown={(event) => {
                if (
                  projectPath &&
                  (event.key === "Enter" || event.key === " ")
                ) {
                  void openFolder(projectPath);
                  event.currentTarget.blur();
                }
              }}
            >
              {projectName}
            </span>{" "}
            下做什么
          </>
        ) : (
          "我们该构建什么"
        )}
      </h2>
      <div className="new-chat-guide-cards">
        {CARDS.map((card) => (
          <div
            key={card.key}
            className={`new-chat-guide-card${disabled ? " disabled" : ""}`}
            role="button"
            tabIndex={disabled ? -1 : 0}
            aria-disabled={disabled}
            onClick={() => {
              if (!disabled) onAction(card.prompt);
            }}
            onKeyDown={(event) => {
              if (!disabled && (event.key === "Enter" || event.key === " ")) {
                onAction(card.prompt);
                event.currentTarget.blur();
              }
            }}
          >
            <span className={`new-chat-guide-card-icon ${card.tone}`}>
              {card.icon}
            </span>
            <span className="new-chat-guide-card-title">{card.title}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
