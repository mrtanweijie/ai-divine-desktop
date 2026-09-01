import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import {
  Check,
  Loader2,
  MessageSquare,
  Settings2,
  Terminal,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CompactResult, ContextUsage } from "@/types";
import { compactSession, getContextUsage } from "@/services/api";
import { Button } from "@/components/ui/Button";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatTokens } from "@/utils";

import "./ContextRingButton.less";

interface ContextRingButtonProps {
  sessionId: string;
  /** External signal to refresh usage (e.g. after each stream "done"). */
  refreshKey?: number;
}

function ringColor(percent: number): string {
  if (percent >= 85) return "var(--color-danger)";
  if (percent >= 60) return "var(--color-warning)";
  return "var(--color-text-muted)";
}

export function ContextRingButton({
  sessionId,
  refreshKey = 0,
}: ContextRingButtonProps) {
  const { t } = useTranslation();
  const [usage, setUsage] = useState<ContextUsage | null>(null);
  const [open, setOpen] = useState(false);
  const [compacting, setCompacting] = useState(false);
  const [panelStyle, setPanelStyle] = useState<CSSProperties>({});
  const anchorRef = useRef<HTMLDivElement>(null);

  const load = async () => {
    try {
      setUsage(await getContextUsage(sessionId));
    } catch {
      setUsage(null);
    }
  };

  useEffect(() => {
    if (!sessionId) {
      setUsage(null);
      return;
    }
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, refreshKey]);

  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    setPanelStyle({
      position: "fixed",
      right: Math.max(8, window.innerWidth - rect.right),
      bottom: window.innerHeight - rect.top + 8,
      zIndex: 60,
    });
    const closeOnOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (anchorRef.current && !anchorRef.current.contains(target)) {
        if (!target?.closest(".context-ring-panel")) setOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const percent = usage?.usedPercent ?? 0;
  const color = ringColor(percent);
  const radius = 8;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - Math.min(percent, 100) / 100);

  const handleCompact = async () => {
    setCompacting(true);
    try {
      const result: CompactResult = await compactSession(sessionId);
      setUsage(result.usage ?? null);
    } catch {
      // keep current usage on failure
    } finally {
      setCompacting(false);
    }
  };

  return (
    <div ref={anchorRef} className="context-ring">
      <Tooltip
        content={t("chat.contextUsageTooltip", "上下文已使用 {{percent}}%", {
          percent,
        })}
      >
        <div
          role="button"
          tabIndex={0}
          className="context-ring-button"
          aria-label={t("chat.contextUsage", "上下文用量")}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setOpen((value) => !value);
            }
          }}
          title={t("chat.contextUsageDetail", "点击查看上下文用量")}
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 22 22"
            className="context-ring-svg"
            aria-hidden="true"
          >
            <circle
              cx="11"
              cy="11"
              r={radius}
              fill="none"
              stroke="var(--color-border)"
              strokeWidth="2"
            />
            <circle
              cx="11"
              cy="11"
              r={radius}
              fill="none"
              stroke={color}
              strokeWidth="2"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
              transform="rotate(-90 11 11)"
              style={{ transition: "stroke-dashoffset 0.3s ease, stroke 0.3s ease" }}
            />
          </svg>
        </div>
      </Tooltip>

      {open &&
        createPortal(
          <div className="context-ring-panel" style={panelStyle} role="dialog">
            <div className="context-ring-summary">
              <span className="context-ring-label">
                {t("chat.contextUsed", "上下文已用")}
                <span className="context-ring-percent" style={{ color }}>
                  {percent}%
                </span>
              </span>
              <span className="context-ring-window">
                {`~${formatTokens(usage?.estimatedTokens ?? 0)}`} /{" "}
                {`~${formatTokens(usage?.contextWindow ?? 0)}`}
              </span>
            </div>
            <div
              className="context-ring-bar"
              role="progressbar"
              aria-valuenow={Math.min(percent, 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="context-ring-bar-fill"
                style={{
                  width: `${Math.min(percent, 100)}%`,
                  background: color,
                }}
              />
            </div>
            <div className="context-ring-breakdown">
              <div className="context-ring-row">
                <Terminal size={12} className="context-ring-row-icon" />
                <span className="context-ring-row-label">
                  {t("chat.contextSystemPrompt", "系统提示词")}
                </span>
                <span>{`~${formatTokens(usage?.breakdown.systemPrompt ?? 0)}`}</span>
              </div>
              <div className="context-ring-row">
                <Settings2 size={12} className="context-ring-row-icon" />
                <span className="context-ring-row-label">
                  {t("chat.contextTools", "工具")}
                </span>
                <span>{`~${formatTokens(usage?.breakdown.tools ?? 0)}`}</span>
              </div>
              <div className="context-ring-row">
                <MessageSquare size={12} className="context-ring-row-icon" />
                <span className="context-ring-row-label">
                  {t("chat.contextMessages", "对话消息")}
                </span>
                <span>{`~${formatTokens(usage?.breakdown.messages ?? 0)}`}</span>
              </div>
            </div>
            <Button
              variant="ghost"
              size="small"
              type="button"
              className="context-ring-compact"
              onClick={() => void handleCompact()}
              disabled={compacting || !usage?.compactable}
            >
              {compacting ? (
                <Loader2 size={13} className="context-ring-spin" />
              ) : usage?.hasSummary ? (
                <Check size={13} />
              ) : (
                <Zap size={13} />
              )}
              <span>
                {usage?.hasSummary
                  ? t("chat.contextCompacted", "已压缩")
                  : t("chat.compactContext", "压缩上下文")}
              </span>
            </Button>
          </div>,
          document.body
        )}
    </div>
  );
}
