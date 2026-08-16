import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useChatStreamContext } from "@/pages/chat/hooks/ChatStreamContext";

export interface ChoiceOption {
  label: string;
  theme?: string;
  desc?: string;
}

export interface ChoiceBlockData {
  title?: string;
  options: ChoiceOption[];
  other?: boolean;
}

/** 从 ```options 代码块中解析选项数据；解析失败返回 null。 */
export function parseOptionsBlock(code: string): ChoiceBlockData | null {
  const text = (code || "").trim();
  let start = text.indexOf("{");
  let end = text.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    const data = JSON.parse(text.slice(start, end + 1));
    if (!data || !Array.isArray(data.options) || data.options.length === 0) {
      return null;
    }
    const options: ChoiceOption[] = data.options
      .filter(
        (item: unknown): item is ChoiceOption =>
          !!item &&
          typeof item === "object" &&
          typeof (item as ChoiceOption).label === "string"
      )
      .map((item: ChoiceOption) => ({
        label: String(item.label).trim(),
        theme: item.theme ? String(item.theme) : undefined,
        desc: item.desc ? String(item.desc) : undefined,
      }));
    if (options.length === 0) return null;
    return {
      title: data.title ? String(data.title) : undefined,
      options,
      other: Boolean(data.other),
    };
  } catch {
    return null;
  }
}

export function ChoiceBlock({ data }: { data: ChoiceBlockData }) {
  const { t } = useTranslation();
  const { sendMessage, effort } = useChatStreamContext();
  const [selected, setSelected] = useState<string | null>(null);
  const [custom, setCustom] = useState("");
  const [sentCustom, setSentCustom] = useState(false);

  const options = useMemo(
    () => (Array.isArray(data?.options) ? data.options : []),
    [data]
  );
  if (options.length === 0) return null;

  const finished = selected !== null || sentCustom;

  const pick = (label: string) => {
    setSelected(label);
    sendMessage(label, [], effort);
  };

  const sendCustom = () => {
    const text = custom.trim();
    if (!text || finished) return;
    setSentCustom(true);
    sendMessage(text, [], effort);
  };

  return (
    <div className="choice-block">
      {data?.title && <div className="choice-title">{data.title}</div>}
      <div className="choice-options">
        {options.map((opt) => (
          <Button
            key={opt.label}
            variant="secondary"
            size="medium"
            className={`choice-option${
              selected === opt.label ? " selected" : ""
            }`}
            onClick={() => pick(opt.label)}
            disabled={finished}
          >
            <span className="choice-option-label">{opt.label}</span>
            {opt.desc && (
              <span className="choice-option-desc">{opt.desc}</span>
            )}
          </Button>
        ))}
      </div>
      {data?.other && (
        <div className="choice-other">
          <Input
            className="choice-other-input"
            placeholder={t(
              "chat.choiceOtherPlaceholder",
              "其他风格，直接输入…"
            )}
            value={custom}
            onChange={(event) => setCustom(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") sendCustom();
            }}
            disabled={finished}
          />
          <Button
            variant="primary"
            size="medium"
            className="choice-other-send"
            onClick={sendCustom}
            disabled={finished || !custom.trim()}
          >
            <Send size={13} />
            <span>{t("chat.choiceOtherSend", "选择")}</span>
          </Button>
        </div>
      )}
      {finished && (
        <div className="choice-note">
          {t("chat.choiceSelected", "已选择，正在生成…")}
        </div>
      )}
    </div>
  );
}
