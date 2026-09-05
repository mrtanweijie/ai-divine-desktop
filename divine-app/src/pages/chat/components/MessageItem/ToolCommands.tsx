// Terminal command display (non-confirm state).
import { useTranslation } from "react-i18next";
import type { ToolEvent } from "@/types";

export function ToolCommands({
  tool,
  commandsOpen,
  onToggleCommands,
}: {
  tool: ToolEvent;
  commandsOpen: boolean;
  onToggleCommands: () => void;
}) {
  const { t } = useTranslation();
  if (tool.status === "confirm") return null;
  if (!tool.commands?.length && !tool.command) return null;

  if (tool.commands?.length) {
    return (
      <div className="terminal-commands">
        {tool.commands.slice(0, commandsOpen ? tool.commands.length : 3).map((command) => (
          <div className="terminal-command" key={command}>
            <span className="terminal-command-prompt">$</span>
            <code>{command}</code>
          </div>
        ))}
        {tool.commands.length > 3 && !commandsOpen && (
          <div
            role="button"
            tabIndex={0}
            className="terminal-commands-more"
            onClick={onToggleCommands}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onToggleCommands();
              }
            }}
          >
            {t("tool.expandCommands", "展开全部 {{count}} 条命令", {
              count: tool.commands.length,
            })}
          </div>
        )}
      </div>
    );
  }
  return (
    <div className="terminal-command">
      <span className="terminal-command-prompt">$</span>
      <code>{tool.command}</code>
    </div>
  );
}
