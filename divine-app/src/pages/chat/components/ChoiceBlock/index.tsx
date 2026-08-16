import { useMemo, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useChatStreamContext } from "@/pages/chat/hooks/ChatStreamContext";

export interface ChoiceOption {
  label: string;
  theme?: string;
  color_scheme?: string;
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
        color_scheme: item.color_scheme
          ? String(item.color_scheme)
          : undefined,
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

  // 隐藏的主题色（前端兜底过滤，无论 LLM 输出什么都不展示）
  const HIDDEN_THEME_KEYS: ReadonlySet<string> = new Set([
    "iceblue",
    "duskmauve",
    "lotuspink",
    "pureblack",
  ]);

  // 主题色副标题（前端兜底覆盖：卡片 desc 由 LLM 自由生成，
  // 常从历史复现旧文案，已知主题一律用内置文案替换）
  const THEME_DESCS: Record<string, string> = {
    teal: "青绿 + 琥珀暖，经典雅致",
    iceblue: "冰川质感",
    desert: "暖沙 + 落日金，辽阔热烈",
    vintage: "暖灰 + 古铜棕，怀旧胶片",
    midnight: "墨蓝 + 夜紫，深邃静谧",
    pureblack: "极简纯黑",
    mistsage: "雾灰青 + 灰白，清冷淡雅",
    mistblue: "灰蓝 + 浅雾蓝，宁静柔和",
    duskmauve: "灰紫 + 淡藕色，温柔雅致",
    lotuspink: "藕粉 + 暖灰，温暖不甜腻",
    dunesand: "暖米沙 + 浅卡其，自然质朴",
    smokegray: "暖灰 + 银灰，极简克制",
  };

  const options = useMemo(
    () =>
      (Array.isArray(data?.options) ? data.options : [])
        .filter(
          (opt) =>
            !opt.color_scheme || !HIDDEN_THEME_KEYS.has(opt.color_scheme)
        )
        .map((opt) =>
          opt.color_scheme && THEME_DESCS[opt.color_scheme]
            ? { ...opt, desc: THEME_DESCS[opt.color_scheme] }
            : opt
        ),
    [data]
  );
  if (options.length === 0) return null;

  // 主题色卡模式：选项带 color_scheme 时用紧凑色卡网格展示
  const isSwatchMode = options.some((opt) => !!opt.color_scheme);

  // 主题色预览色（与后端 TRAVEL_MAG_THEMES 主色一致，供色卡展示）
  const SWATCH_COLORS: Record<string, string> = {
    teal: "#2A5A5B",
    iceblue: "#3A6B8C",
    desert: "#8B4513",
    vintage: "#5F5E5A",
    midnight: "#1A1A2E",
    pureblack: "#000000",
    mistsage: "#8AB5B0",
    mistblue: "#8AA8C0",
    duskmauve: "#9A8AAB",
    lotuspink: "#C4A098",
    dunesand: "#BCAE92",
    smokegray: "#A8A7A0",
  };

  // 底部色板（深/主/浅/点缀四色，与后端 TRAVEL_MAG_THEMES 一致；
  // 淡雅系列主色=teal-400、点缀=teal-800，其余沿用默认阶梯）
  const SWATCH_PALETTES: Record<string, string[]> = {
    teal: ["#162E2F", "#2A5A5B", "#8CC0C1", "#C08552"],
    iceblue: ["#0F2638", "#2C5775", "#7EAEC9", "#6B9BBA"],
    desert: ["#3D2510", "#8B4513", "#DDB56A", "#D49142"],
    vintage: ["#2C2C2A", "#5F5E5A", "#B4B2A9", "#A6772E"],
    midnight: ["#16161E", "#3A3A5C", "#5A5A7E", "#807CA8"],
    pureblack: ["#0A0A0A", "#242424", "#3A3A3A", "#707070"],
    mistsage: ["#2A4540", "#8AB5B0", "#C8DDD9", "#3A5A56"],
    mistblue: ["#2A4858", "#8AA8C0", "#C8D8E4", "#3A5870"],
    duskmauve: ["#382A48", "#9A8AAB", "#CCC4D6", "#4A3A5C"],
    lotuspink: ["#4A342E", "#C4A098", "#DAC8C5", "#6A4A42"],
    dunesand: ["#403828", "#BCAE92", "#DCD4BE", "#5C5240"],
    smokegray: ["#343430", "#A8A7A0", "#D2D0CC", "#4A4945"],
  };

  const finished = selected !== null || sentCustom;

  const pick = (opt: ChoiceOption) => {
    setSelected(opt.label);
    // 带 color_scheme 的选项（主题色卡片）：发送「label（color_scheme）」让 Agent 明确传配色
    const msg = opt.color_scheme
      ? `${opt.label}（${opt.color_scheme}）`
      : opt.label;
    sendMessage(msg, [], effort);
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
      {isSwatchMode ? (
        <div className="choice-swatches">
          {options.map((opt) => {
            const color = opt.color_scheme
              ? SWATCH_COLORS[opt.color_scheme] || "#ccc"
              : "#ccc";
            const palette = opt.color_scheme
              ? SWATCH_PALETTES[opt.color_scheme] || null
              : null;
            return (
              <div
                key={opt.label}
                role="button"
                tabIndex={finished ? -1 : 0}
                aria-disabled={finished}
                className={`choice-swatch${
                  selected === opt.label ? " selected" : ""
                }${finished ? " disabled" : ""}`}
                onClick={() => pick(opt)}
                style={{ "--swatch": color } as CSSProperties}
              >
                <span className="choice-swatch-title">{opt.label}</span>
                {opt.desc && (
                  <span className="choice-swatch-desc">{opt.desc}</span>
                )}
                {palette && (
                  <span className="choice-swatch-palette">
                    {palette.map((c, i) => (
                      <span
                        key={i}
                        className="choice-swatch-chip"
                        style={{ backgroundColor: c }}
                      />
                    ))}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="choice-options">
          {options.map((opt) => (
            <Button
              key={opt.label}
              variant="secondary"
              size="medium"
              className={`choice-option${
                selected === opt.label ? " selected" : ""
              }`}
              onClick={() => pick(opt)}
              disabled={finished}
            >
              <span className="choice-option-label">{opt.label}</span>
              {opt.desc && (
                <span className="choice-option-desc">{opt.desc}</span>
              )}
            </Button>
          ))}
        </div>
      )}
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
