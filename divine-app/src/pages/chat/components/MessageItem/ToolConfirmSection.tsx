// Approval confirm sections: terminal / external file / plan / calendar /
// skill migrate / skill install / subagents write.
import {
  CalendarDays,
  FileCode2,
  FolderOpen,
  GitBranch,
  Group,
  ListChecks,
  TerminalSquare,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import type { ToolEvent } from "@/types";
import { AskUserForm } from "./AskUserForm";

function ConfirmButtons({
  deciding,
  disabled,
  onDecide,
  allowLabel,
  rejectLabel,
}: {
  deciding: boolean;
  disabled?: boolean;
  onDecide: (allow: boolean) => void;
  allowLabel: string;
  rejectLabel: string;
}) {
  return (
    <Flex align="center" gap={8}>
      <Button size="small" loading={deciding} disabled={disabled} onClick={() => onDecide(true)}>
        {allowLabel}
      </Button>
      <Button
        size="small"
        variant="ghost"
        disabled={disabled || deciding}
        onClick={() => onDecide(false)}
      >
        {rejectLabel}
      </Button>
    </Flex>
  );
}

export function ToolConfirmSection({
  tool,
  deciding,
  targetSessionId,
  onDecide,
}: {
  tool: ToolEvent;
  deciding: boolean;
  targetSessionId?: string | null;
  onDecide: (allow: boolean) => void;
}) {
  const { t } = useTranslation();
  const confirmDisabled = !targetSessionId;

  if (tool.status !== "confirm") return null;

  // ask_user：agent 主动提问，内联收集补充信息（text / single_choice）
  if (tool.confirm_type === "ask_user") {
    return (
      <div className="terminal-confirm ask-user-confirm">
        <AskUserForm
          question={tool.question || tool.message}
          options={tool.options ?? []}
          inputType={tool.input_type === "single_choice" ? "single_choice" : "text"}
          callId={tool.call_id}
          targetSessionId={targetSessionId}
          disabled={confirmDisabled}
        />
      </div>
    );
  }

  // Git 写操作确认（git_commit / git_revert）：必须放在下方带 command
  // 的终端通用分支之前，否则会被截走显示成「终端命令确认」
  if (tool.confirm_type === "git") {
    return (
      <div className="terminal-confirm git-confirm">
        <div className="terminal-confirm-head">
          <GitBranch size={14} />
          <span>{t("tool.gitConfirm", "Git 写操作确认")}</span>
        </div>
        <pre>{tool.command || tool.message}</pre>
        <ConfirmButtons
          deciding={deciding}
          disabled={confirmDisabled}
          onDecide={onDecide}
          allowLabel={t("tool.allowRun", "允许执行")}
          rejectLabel={t("tool.reject", "拒绝")}
        />
      </div>
    );
  }

  // 终端命令确认（external_file 特殊处理，见下）
  if (tool.confirm_type !== "external_file" && tool.command) {
    return (
      <div className="terminal-confirm">
        <div className="terminal-confirm-head">
          <TerminalSquare size={14} />
          <span>{t("tool.terminalConfirm", "终端命令确认")}</span>
        </div>
        <pre>{tool.command}</pre>
        <ConfirmButtons
          deciding={deciding}
          onDecide={onDecide}
          allowLabel={t("tool.allowRun", "允许执行")}
          rejectLabel={t("tool.reject", "拒绝")}
        />
      </div>
    );
  }

  if (tool.confirm_type === "external_file") {
    return (
      <div className="terminal-confirm external-file-confirm">
        <div className="terminal-confirm-head">
          <FolderOpen size={14} />
          <span>{t("tool.externalFileConfirm", "外部文件访问确认")}</span>
        </div>
        <pre>{(tool.paths ?? [tool.command]).join("\n")}</pre>
        <ConfirmButtons
          deciding={deciding}
          onDecide={onDecide}
          allowLabel={t("tool.allowAccess", "允许访问")}
          rejectLabel={t("tool.reject", "拒绝")}
        />
      </div>
    );
  }

  if (tool.confirm_type === "plan") {
    return (
      <div className="terminal-confirm plan-confirm">
        <div className="terminal-confirm-head">
          <ListChecks size={14} />
          <span>{t("tool.planConfirm", "执行计划确认")}</span>
        </div>
        <p className="plan-confirm-text">
          {t("tool.planConfirmText", "计划已创建，是否开始执行？")}
        </p>
        <ConfirmButtons
          deciding={deciding}
          disabled={confirmDisabled}
          onDecide={onDecide}
          allowLabel={t("tool.startExecution", "开始执行")}
          rejectLabel={t("common.cancel", "取消")}
        />
      </div>
    );
  }

  if (tool.confirm_type === "preprocess_fallback") {
    return (
      <div className="terminal-confirm preprocess-fallback-confirm">
        {/* 标题与文案由共享头部（tool-name + tool-message）展示，
            这里只渲染操作按钮，避免重复 */}
        <ConfirmButtons
          deciding={deciding}
          disabled={confirmDisabled}
          onDecide={onDecide}
          allowLabel={t("tool.preprocessContinueCloud", "继续走云端")}
          rejectLabel={t("tool.preprocessCancel", "取消")}
        />
      </div>
    );
  }

  if (tool.confirm_type === "plan_choice") {
    return (
      <div className="terminal-confirm plan-choice-confirm">
        <div className="terminal-confirm-head">
          <ListChecks size={14} />
          <span>{t("tool.planChoiceConfirm", "方案确认")}</span>
        </div>
        <p className="plan-confirm-text">
          {t("tool.planChoiceText", "执行任务前是否先出一份方案？")}
        </p>
        <ConfirmButtons
          deciding={deciding}
          onDecide={onDecide}
          allowLabel={t("tool.planFirst", "先出方案")}
          rejectLabel={t("tool.executeDirectly", "直接执行")}
        />
      </div>
    );
  }

  if (tool.confirm_type === "write_calendar") {
    return (
      <div className="terminal-confirm calendar-confirm">
        <div className="terminal-confirm-head">
          <CalendarDays size={14} />
          <span>{t("tool.calendarConfirm", "写入日程确认")}</span>
        </div>
        <p className="plan-confirm-text">
          {t("tool.calendarConfirmText", "是否同时写入日程？")}
        </p>
        <ConfirmButtons
          deciding={deciding}
          onDecide={onDecide}
          allowLabel={t("tool.writeCalendar", "写入日程")}
          rejectLabel={t("common.cancel", "取消")}
        />
      </div>
    );
  }

  if (tool.confirm_type === "skill_migrate") {
    return (
      <div className="terminal-confirm skill-migrate-confirm">
        <div className="terminal-confirm-head">
          <FileCode2 size={14} />
          <span>{t("tool.skillMigrateConfirm", "技能迁移确认")}</span>
        </div>
        <div className="skill-migrate-meta">
          <span className="skill-migrate-name">
            {tool.skill_migrate?.name ?? tool.message}
          </span>
          <span>
            {t("tool.sourceTarget", "来源：{{source}} · 目标：{{target}}", {
              source: tool.skill_migrate?.source_tool ?? t("tool.unknown", "未知"),
              target:
                tool.target === "user"
                  ? t("tool.targetUser", "用户级 ~/.divine/skills")
                  : t("tool.targetProject", "项目 .divine/skills"),
            })}
          </span>
          {tool.skill_migrate?.description && (
            <span className="skill-migrate-description">
              {tool.skill_migrate.description}
            </span>
          )}
        </div>
        <pre>{tool.skill_migrate?.preview ?? tool.message}</pre>
        <ConfirmButtons
          deciding={deciding}
          disabled={confirmDisabled}
          onDecide={onDecide}
          allowLabel={t("tool.confirmMigrate", "确认迁移")}
          rejectLabel={t("common.cancel", "取消")}
        />
      </div>
    );
  }

  if (tool.confirm_type === "skill_migrate_batch") {
    return (
      <div className="terminal-confirm skill-migrate-confirm">
        <div className="terminal-confirm-head">
          <FileCode2 size={14} />
          <span>{t("tool.batchMigrateConfirm", "批量技能迁移确认")}</span>
        </div>
        <div className="skill-migrate-meta">
          <span className="skill-migrate-name">
            {t("tool.skillsToMigrate", "{{count}} 个技能待迁移", {
              count: tool.skill_migrations?.length ?? 0,
            })}
          </span>
          <span>
            {t("tool.targetLabel", "目标：{{target}}", {
              target:
                tool.target === "user"
                  ? t("tool.targetUser", "用户级 ~/.divine/skills")
                  : t("tool.targetProject", "项目 .divine/skills"),
            })}
          </span>
        </div>
        <div className="skill-migration-list">
          {tool.skill_migrations?.map((skill) => (
            <div className="skill-migration-item" key={skill.name}>
              <span className="skill-migration-item-name">{skill.name}</span>
              <span className="skill-migration-item-source">
                {skill.source_tool}
              </span>
              {skill.existing && (
                <span className="skill-migration-item-existing">
                  {t("tool.existingSkip", "已存在，将跳过")}
                </span>
              )}
              {skill.description && (
                <span className="skill-migration-item-description">
                  {skill.description}
                </span>
              )}
            </div>
          ))}
        </div>
        <pre>
          {tool.skill_migrations
            ?.map(
              (skill) =>
                `## ${skill.name} (${skill.source_tool})\n${skill.preview}`
            )
            .join("\n\n---\n\n") ?? tool.message}
        </pre>
        <ConfirmButtons
          deciding={deciding}
          disabled={confirmDisabled}
          onDecide={onDecide}
          allowLabel={t("tool.confirmAllMigrate", "确认全部迁移")}
          rejectLabel={t("common.cancel", "取消")}
        />
      </div>
    );
  }

  if (tool.confirm_type === "skill_install") {
    return (
      <div className="terminal-confirm skill-migrate-confirm">
        <div className="terminal-confirm-head">
          <FileCode2 size={14} />
          <span>{t("tool.gitHubInstallConfirm", "GitHub 技能安装确认")}</span>
        </div>
        <div className="skill-migrate-meta">
          <span className="skill-migrate-name">
            {tool.skill_install?.skills?.[0]?.name ?? tool.skill_install?.repo ?? tool.message}
          </span>
          <span>
            {t("tool.repoTarget", "仓库：{{repo}} · 目标：{{target}}", {
              repo: tool.skill_install?.repo ?? t("tool.unknown", "未知"),
              target:
                tool.target === "user"
                  ? t("tool.targetUser", "用户级 ~/.divine/skills")
                  : t("tool.targetProject", "项目 .divine/skills"),
            })}
          </span>
          {tool.skill_install && tool.skill_install.skills.length > 1 && (
            <span>
              {t("tool.repoContains", "仓库包含 {{count}} 个技能：", {
                count: tool.skill_install.skills.length,
              })}
              {tool.skill_install.skills
                .map(
                  (skill) =>
                    `${skill.name} (${skill.skill_path || t("tool.repoRoot", "仓库根目录")})`
                )
                .join(t("tasks.dayJoin", "、"))}
            </span>
          )}
          {tool.skill_install?.skills?.[0]?.description && (
            <span className="skill-migrate-description">
              {tool.skill_install.skills[0].description}
            </span>
          )}
        </div>
        <pre>{tool.skill_install?.skills?.[0]?.preview ?? tool.message}</pre>
        <ConfirmButtons
          deciding={deciding}
          disabled={confirmDisabled}
          onDecide={onDecide}
          allowLabel={t("tool.confirmInstall", "确认安装")}
          rejectLabel={t("common.cancel", "取消")}
        />
      </div>
    );
  }

  if (tool.confirm_type === "subagents_write") {
    return (
      <div className="terminal-confirm subagents-write-confirm">
        <div className="terminal-confirm-head">
          <Group size={14} />
          <span>{t("tool.subagentsWriteConfirm", "并行写任务确认")}</span>
        </div>
        <p className="plan-confirm-text">
          {t("tool.subagentsWriteText", "以下子任务将并行创建/修改文件，是否确认执行？")}
        </p>
        <div className="subagents-write-list">
          {tool.subagent_write?.tasks.map((task) => (
            <div className="subagents-write-item" key={task.id}>
              <span className="subagents-write-item-name">{task.name}</span>
              <span className="subagents-write-item-paths">
                {(task.write_paths ?? []).join(", ") || t("tool.unknown", "未知")}
              </span>
            </div>
          ))}
        </div>
        <ConfirmButtons
          deciding={deciding}
          disabled={confirmDisabled}
          onDecide={onDecide}
          allowLabel={t("tool.confirmWrite", "确认执行")}
          rejectLabel={t("common.cancel", "取消")}
        />
      </div>
    );
  }

  // 兜底：后端新增中断类型而前端未跟进时，也必须给出可操作的确认
  // 按钮——此前这里返回 null，git_commit 中断（无 confirm_type）就
  // 因此没有任何按钮，用户无从回应、Agent 卡到 180s 超时被拒。
  return (
    <div className="terminal-confirm">
      <pre>{tool.message}</pre>
      <ConfirmButtons
        deciding={deciding}
        disabled={confirmDisabled}
        onDecide={onDecide}
        allowLabel={t("tool.allowRun", "允许执行")}
        rejectLabel={t("tool.reject", "拒绝")}
      />
    </div>
  );
}
