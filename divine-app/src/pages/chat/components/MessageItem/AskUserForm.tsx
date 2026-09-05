// AskUserForm: inline answer card for ask_user interrupts.
//
// Shown while a tool card is in `confirm` state with confirm_type=ask_user.
// The agent paused and is waiting for the user's answer; submitting POSTs to
// /chat/answer which wakes the orchestrator and resumes the run with the
// answer as the tool result.
//
// V1 supports free text and single-choice options (multi_choice deferred).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, Check } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { request } from "@/services/request";

interface AskUserFormProps {
  question: string;
  options?: string[];
  inputType?: "text" | "single_choice";
  callId?: string;
  targetSessionId?: string | null;
  disabled?: boolean;
}

export function AskUserForm({
  question,
  options = [],
  inputType = "text",
  callId,
  targetSessionId,
  disabled,
}: AskUserFormProps) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 乐观冻结：提交成功即本地置 answered（不等待后端 done 事件）；
  // 失败则回退到可编辑态并展示错误。
  const [answered, setAnswered] = useState<string | null>(null);

  const canSubmit =
    !submitting &&
    !answered &&
    !disabled &&
    Boolean(targetSessionId) &&
    (inputType === "single_choice" ? selected !== null : text.trim().length > 0);

  const submit = async (answer: string) => {
    const trimmed = answer.trim();
    if (!trimmed || submitting || answered) return;
    setSubmitting(true);
    setError(null);
    setAnswered(trimmed); // optimistic freeze
    try {
      const result = await request<{ ok?: boolean; message?: string }>("/chat/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: targetSessionId,
          call_id: callId ?? "",
          answer: trimmed,
        }),
      });
      if (result && result.ok === false) {
        setAnswered(null);
        setError(result.message || t("tool.answerFailed", "回答发送失败，请重试"));
      }
    } catch {
      setAnswered(null);
      setError(t("tool.answerFailed", "回答发送失败，请重试"));
    } finally {
      setSubmitting(false);
    }
  };

  const chooseOption = (option: string) => {
    if (answered || disabled) return;
    setSelected(option);
    setError(null);
  };

  const onOptionKeyDown = (event: React.KeyboardEvent, option: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      chooseOption(option);
    }
  };

  return (
    <div className="ask-user-form">
      {answered !== null ? (
        <div className="ask-user-answered">
          <span className="ask-user-answered-label">
            <Check size={12} />
            {t("tool.askUserAnswerLabel", "你的回答")}
          </span>
          <blockquote className="ask-user-answer-quote">{answered}</blockquote>
        </div>
      ) : (
        <>
          <p className="ask-user-hint">
            {t("tool.askUserHint", "回答后 Agent 将带着你的补充继续任务")}
          </p>
          {inputType === "single_choice" && options.length > 0 ? (
            <div className="ask-user-options" role="radiogroup">
              {options.map((option) => {
                const active = selected === option;
                return (
                  <div
                    key={option}
                    role="radio"
                    aria-checked={active}
                    tabIndex={0}
                    className={`ask-user-option${active ? " active" : ""}`}
                    onClick={() => chooseOption(option)}
                    onKeyDown={(event) => onOptionKeyDown(event, option)}
                  >
                    <span className="ask-user-option-radio" aria-hidden>
                      {active && <Check size={11} />}
                    </span>
                    <span className="ask-user-option-text">{option}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <TextArea
              className="ask-user-input"
              rows={question.length > 60 ? 3 : 1}
              value={text}
              placeholder={t("tool.askUserPlaceholder", "输入补充信息…")}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && canSubmit) {
                  event.preventDefault();
                  void submit(text);
                }
              }}
            />
          )}
          <div className="ask-user-actions">
            {error && (
              <span className="ask-user-error" role="alert">
                {error}
              </span>
            )}
            <Button
              size="small"
              loading={submitting}
              disabled={!canSubmit}
              onClick={() => void submit(inputType === "single_choice" ? (selected ?? "") : text)}
            >
              <ArrowUpRight size={14} />
              {t("tool.askUserSubmit", "发送回答")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
