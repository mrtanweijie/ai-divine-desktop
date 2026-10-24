import { useEffect, useRef, useState } from "react";
import { ChevronDown, Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BrowserStepItem } from "@/types";

import "./index.less";

interface BrowserStepsCardProps {
  steps: BrowserStepItem[];
  streaming?: boolean;
}

/**
 * browser 子 Agent 的操作步骤时间线（design 031 §4 SSE 契约扩展）。
 * 每行显示步号、工具名（去 browser_ 前缀）、页面标题或 URL。
 */
export function BrowserStepsCard({ steps, streaming }: BrowserStepsCardProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const last = steps[steps.length - 1];

  // 有新步骤流入时保持展开（流结束后不强制收起，尊重用户当前状态）
  useEffect(() => {
    if (streaming && !detailsRef.current?.open) {
      setOpen(true);
    }
  }, [steps.length, streaming]);

  const toggle = () => setOpen((value) => !value);
  const shortTool = (tool: string) => tool.replace(/^browser_/, "");

  return (
    <details
      className="subagent-block browser-steps-block"
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
        <Globe size={13} />
        <span className="subagent-title">{t("message.browserSteps", "浏览器操作")}</span>
        <span className="subagent-progress">{steps.length}</span>
        {!open && streaming && last ? (
          <span className="subagent-preview">{shortTool(last.tool)}</span>
        ) : null}
      </summary>
      <div className="subagent-items">
        {steps.map((item) => (
          <div key={item.step} className="subagent-item browser-step-item">
            <span className="browser-step-no">{item.step}</span>
            <span className="browser-step-tool">{shortTool(item.tool)}</span>
            {item.title ? (
              <span className="browser-step-title" title={item.title}>
                {item.title}
              </span>
            ) : item.url ? (
              <span className="browser-step-title" title={item.url}>
                {item.url}
              </span>
            ) : null}
          </div>
        ))}
      </div>
    </details>
  );
}
