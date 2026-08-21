import { useEffect, useRef, useState } from "react";
import { AlertCircle, Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SubAgentItem } from "@/types";

import "./index.less";

interface SubAgentPanelProps {
  subagents: SubAgentItem[];
  streaming?: boolean;
}

/**
 * Collapsible progress panel for parallel sub-agent runs.
 * Each row shows a status icon (spinner / done / error), the sub-task name,
 * and a one-line summary or error (full text on hover via title).
 */
export function SubAgentPanel({ subagents, streaming }: SubAgentPanelProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const anyRunning = subagents.some((item) => item.status === "running");
  const done = subagents.filter((item) => item.status === "done").length;

  // Auto-expand while anything is still running; once everything settles,
  // keep the user's current toggle state (no forced collapse).
  useEffect(() => {
    if (anyRunning && !detailsRef.current?.open) {
      setOpen(true);
    }
  }, [anyRunning]);

  const toggle = () => setOpen((value) => !value);

  return (
    <details
      className="subagent-block"
      open={open}
      ref={detailsRef}
      data-streaming={streaming ? "true" : undefined}
    >
      <summary
        className="subagent-summary"
        onClick={(event) => {
          event.preventDefault();
          toggle();
        }}
      >
        <ChevronDown size={13} className={open ? "expanded" : ""} />
        <span className="subagent-title">
          {t("message.subagents", "子 Agent")}
        </span>
        <span className="subagent-progress">
          {done}/{subagents.length}
        </span>
        {!open && anyRunning && (
          <span className="subagent-preview">
            {t("message.subagentRunning", "运行中…")}
          </span>
        )}
      </summary>
      <div className="subagent-items">
        {subagents.map((item) => (
          <div key={item.id} className={`subagent-item ${item.status}`}>
            <span className="subagent-item-icon">
              {item.status === "done" ? (
                <Check size={13} />
              ) : item.status === "error" ? (
                <AlertCircle size={13} />
              ) : (
                <span className="subagent-spinner" />
              )}
            </span>
            <span className="subagent-item-title">{item.name}</span>
            {item.status === "done" && item.summary ? (
              <span className="subagent-item-summary" title={item.summary}>
                {item.summary}
              </span>
            ) : item.status === "error" && item.error ? (
              <span className="subagent-item-error" title={item.error}>
                {item.error}
              </span>
            ) : null}
          </div>
        ))}
      </div>
    </details>
  );
}
