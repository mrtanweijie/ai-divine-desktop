import { useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  CalendarClock,
  ChartNetwork,
  Compass,
  FileCode2,
  FolderTree,
  GraduationCap,
} from "lucide-react";
import { openFolder } from "@/services/tauri";
import { GrokBallIdle } from "./GrokBallIdle";
import "./index.less";

interface GuideCard {
  key: string;
  icon: ReactNode;
  tone: "blue" | "purple" | "green" | "orange" | "cyan" | "rose";
  title: string;
  description: string;
  prompt: string;
}

interface NewChatGuideProps {
  projectName: string | null;
  projectPath?: string | null;
  cardsVisible?: boolean;
  disabled?: boolean;
  onAction: (prompt: string) => void;
}

export function NewChatGuide({
  projectName,
  projectPath,
  cardsVisible = true,
  disabled = false,
  onAction,
}: NewChatGuideProps) {
  const { t } = useTranslation();
  const cards = useMemo<GuideCard[]>(
    () => [
      {
        key: "analyze",
        icon: <FolderTree size={20} />,
        tone: "blue",
        title: t("guide.analyze", "分析项目"),
        description: t("guide.analyzeDescription", "目录、架构、关键文件"),
        prompt: t(
          "guide.analyzePrompt",
          "请分析当前项目的工作空间目录结构、技术架构和关键文件，并给出总结。"
        ),
      },
      {
        key: "modify",
        icon: <FileCode2 size={20} />,
        tone: "purple",
        title: t("guide.modify", "修改代码"),
        description: t("guide.modifyDescription", "定位问题并批量修改"),
        prompt: t(
          "guide.modifyPrompt",
          "请先查看相关文件，定位问题，再用 edit_files 批量修改并总结改动。"
        ),
      },
      {
        key: "document",
        icon: <GraduationCap size={20} />,
        tone: "green",
        title: t("guide.document", "生成文档"),
        description: t("guide.documentDescription", "Word / PDF / PPT / Excel"),
        prompt: t(
          "guide.documentPrompt",
          "请根据我的需求生成一份合适的文档（Word、PDF、PPT、Excel 或 Markdown）。"
        ),
      },
      {
        key: "research",
        icon: <Compass size={20} />,
        tone: "orange",
        title: t("guide.research", "查资料总结"),
        description: t("guide.researchDescription", "多来源抓取并汇总"),
        prompt: t(
          "guide.researchPrompt",
          "请帮我批量抓取多个相关来源，整理关键信息并给出带链接的总结。"
        ),
      },
      {
        key: "visual",
        icon: <ChartNetwork size={20} />,
        tone: "cyan",
        title: t("guide.visual", "图表与原型"),
        description: t("guide.visualDescription", "图表、SVG、交互页面"),
        prompt: t(
          "guide.visualPrompt",
          "请根据主题生成图表、示意图或可交互的产品原型。"
        ),
      },
      {
        key: "automate",
        icon: <CalendarClock size={20} />,
        tone: "rose",
        title: t("guide.automate", "提醒与技能"),
        description: t("guide.automateDescription", "提醒、日程、技能迁移"),
        prompt: t(
          "guide.automatePrompt",
          "请帮我设置定时提醒或日程，或扫描可迁移的 AI 工具技能。"
        ),
      },
    ],
    [t]
  );
  return (
    <div className="new-chat-guide">
      <div className="new-chat-guide-icon">
        <GrokBallIdle size={88} blush={false} />
      </div>
      {/* i18next-instrument-ignore */}
      <h2 className="new-chat-guide-title">
        {projectName ? (
          <>
            {t("guide.whatToDoInPrefix", "要在")}{" "}
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
            {t("guide.whatToDoInSuffix", " 下做什么")}
          </>
        ) : (
          t("guide.whatToBuild", "我们该构建什么")
        )}
      </h2>
      <div
        className={`new-chat-guide-cards${cardsVisible ? "" : " is-hidden"}`}
        aria-hidden={!cardsVisible}
      >
        {cards.map((card) => (
          <div
            key={card.key}
            className={`new-chat-guide-card${disabled ? " disabled" : ""}`}
            role="button"
            tabIndex={cardsVisible && !disabled ? 0 : -1}
            aria-disabled={!cardsVisible || disabled}
            onClick={() => {
              if (cardsVisible && !disabled) onAction(card.prompt);
            }}
            onKeyDown={(event) => {
              if (
                cardsVisible &&
                !disabled &&
                (event.key === "Enter" || event.key === " ")
              ) {
                onAction(card.prompt);
                event.currentTarget.blur();
              }
            }}
          >
            <span className={`new-chat-guide-card-icon ${card.tone}`}>
              {card.icon}
            </span>
            <span className="new-chat-guide-card-copy">
              <span className="new-chat-guide-card-title">{card.title}</span>
              <span className="new-chat-guide-card-description">
                {card.description}
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
