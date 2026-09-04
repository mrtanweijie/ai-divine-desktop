import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ToolEvent } from "@/types";

interface TraceRun {
  key: string;
  tool: string;
  turn: number;
  duration: number;
  failed: boolean;
  slow: boolean;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * 执行轨迹面板（P2）：把带耗时数据的工具调用按轮次分组画成耗时条。
 * 仅在有 ≥2 次已完成调用时渲染；单次调用没有对比价值。
 * 历史恢复的消息没有 duration_ms（tool_runs 不回灌进 message parts），
 * 自然不显示——只作用于本次流式会话。
 */
export function TracePanel({ tools }: { tools: ToolEvent[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const { groups, total, runCount } = useMemo(() => {
    const runs: TraceRun[] = tools
      .filter(
        (tool) =>
          tool.duration_ms != null &&
          typeof tool.turn === "number" &&
          tool.turn > 0 &&
          tool.status !== "confirm"
      )
      .map((tool) => ({
        key: tool.run_id ?? `${tool.call_id ?? tool.tool}`,
        tool: tool.tool,
        turn: tool.turn as number,
        duration: tool.duration_ms as number,
        failed: tool.status === "error",
        slow: false,
      }));
    const durations = runs.map((run) => run.duration).sort((a, b) => a - b);
    const median = durations[Math.floor(durations.length / 2)] || 1;
    for (const run of runs) {
      run.slow = run.duration > median * 3;
    }
    const grouped: { turn: number; runs: TraceRun[] }[] = [];
    for (const run of runs) {
      const last = grouped[grouped.length - 1];
      if (last && last.turn === run.turn) {
        last.runs.push(run);
      } else {
        grouped.push({ turn: run.turn, runs: [run] });
      }
    }
    const sum = runs.reduce((acc, run) => acc + run.duration, 0);
    return { groups: grouped, total: sum, runCount: runs.length };
  }, [tools]);

  if (runCount < 2) return null;
  const maxDuration = Math.max(
    ...groups.flatMap((group) => group.runs.map((run) => run.duration))
  );

  return (
    <details className="trace-block" open={open}>
      <summary
        className="trace-summary"
        onClick={(event) => {
          event.preventDefault();
          setOpen((value) => !value);
        }}
      >
        <ChevronDown size={13} className={open ? "expanded" : ""} />
        <span>{t("message.trace", "执行轨迹")}</span>
        <span className="trace-progress">
          {t("message.traceMeta", "{{count}} 次调用 · 共 {{total}}", {
            count: runCount,
            total: formatDuration(total),
          })}
        </span>
      </summary>
      <div className="trace-items">
        {groups.map((group) => (
          <div key={group.turn} className="trace-row">
            <span className="trace-turn">T{group.turn}</span>
            <div className="trace-bars">
              {group.runs.map((run) => (
                <div key={run.key} className="trace-bar-row">
                  <span className="trace-bar-name">{run.tool}</span>
                  <div className="trace-bar-track">
                    <div
                      className={`trace-bar${run.slow ? " slow" : ""}${
                        run.failed ? " failed" : ""
                      }`}
                      style={{
                        width: `${Math.max(
                          4,
                          (run.duration / maxDuration) * 100
                        )}%`,
                      }}
                    />
                    <span className="trace-bar-duration">
                      {formatDuration(run.duration)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}
