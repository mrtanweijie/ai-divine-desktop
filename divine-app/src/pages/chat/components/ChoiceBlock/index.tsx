import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Input } from "@/components/ui/Input";
import { useChatStreamContext } from "@/pages/chat/hooks/ChatStreamContext";
import { saveMessageChoiceState } from "@/services/api";

import "./index.less";
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
  /** 多选模式：true 时选项可多选，确认后发回逗号分隔的 label 列表 */
  multiple?: boolean;
}

/**
 * 修复 LLM 生成的 JSON 中未转义的内部引号。
 * 逐字符扫描，区分 JSON 字符串边界和字符串内的裸引号。
 */
function sanitizeJsonQuotes(raw: string): string {
  const out: string[] = [];
  let inString = false;
  let i = 0;
  while (i < raw.length) {
    const ch = raw[i];
    if (inString) {
      if (ch === "\\") {
        out.push(ch, raw[i + 1] ?? "");
        i += 2;
        continue;
      }
      if (ch === '"') {
        // 判断这个 " 是否是字符串结束符：
        // 如果后面跟 , } ] : 或空白+这些字符，视为正常结束
        const rest = raw.slice(i + 1).trimStart();
        if (!rest || /^[,\}\]:]/.test(rest)) {
          inString = false;
          out.push(ch);
        } else {
          // 字符串内的裸引号，转义为 \u0022
          out.push("\u0022");
        }
      } else {
        out.push(ch);
      }
    } else {
      if (ch === '"') {
        inString = true;
      }
      out.push(ch);
    }
    i++;
  }
  return out.join("");
}

/**
 * 从 ```options 代码块中解析选项数据；解析失败返回 null。
 * 自动修复 LLM 生成的常见 JSON 格式问题（如字符串值内未转义的引号）。
 */
export function parseOptionsBlock(code: string): ChoiceBlockData | null {
  const text = (code || "").trim();
  let start = text.indexOf("{");
  let end = text.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  const raw = text.slice(start, end + 1);
  let data: Record<string, unknown> | null = null;
  try {
    data = JSON.parse(raw);
  } catch {
    // LLM 常在 desc/label 中生成未转义的中文引号，尝试逐字符修复
    try {
      data = JSON.parse(sanitizeJsonQuotes(raw));
    } catch {
      return null;
    }
  }
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
  // 含「暂时不用」选项 = 后续询问卡片（下一步做什么/是否生成产物）：
  // 纯点选，禁用自定义输入框（模型即使写了 other:true 也强制关闭）；
  // 副标题兜底：模型漏写 desc 时统一补「后续有需求再继续任务」
  const declineDesc = "后续有需求再继续任务";
  const optionsFilled = options.map((item) =>
    item.label === "暂时不用"
      ? { ...item, desc: item.desc || declineDesc }
      : item
  );
  const hasDecline = optionsFilled.some((item) => item.label === "暂时不用");
  return {
    title: data.title ? String(data.title) : undefined,
    options: optionsFilled,
    other: hasDecline ? false : Boolean(data.other),
    multiple: hasDecline ? false : Boolean(data.multiple),
  };
}

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

/** 模块级选择记录：key = 消息id|标题|选项label列表。
 * 选择状态跟随消息（不跨会话污染：不同消息即使标题/选项相同也独立），
 * 组件卸载/重挂载后仍保持置灰。 */
interface ChoiceState {
  selected: string | null;
  sentCustom: boolean;
  /** 机器可读主题 key（如 mistblue），便于后续统计/复用 */
  color_scheme?: string | null;
}
const choiceStateStore = new Map<string, ChoiceState>();

function choiceStoreKey(data: ChoiceBlockData, messageId?: string): string {
  const base = `${data.title ?? ""}|${(data.options || [])
    .map((o) => o.label)
    .join(",")}`;
  return messageId ? `${messageId}|${base}` : base;
}

export function ChoiceBlock({
  data,
  messageId,
  persistedChoice,
}: {
  data: ChoiceBlockData;
  messageId?: string;
  /** 从消息 choice_state 读到的已选状态（DB 持久化，刷新/重开会话后保持） */
  persistedChoice?: Record<string, unknown> | null;
}) {
  const { t } = useTranslation();
  const { sendMessage, effort } = useChatStreamContext();
  const storeKey = useMemo(() => choiceStoreKey(data, messageId), [
    data,
    messageId,
  ]);
  const [selected, setSelected] = useState<string | null>(
    () =>
      (persistedChoice?.selected as string | undefined) ??
      choiceStateStore.get(storeKey)?.selected ??
      null
  );
  const [selectedMulti, setSelectedMulti] = useState<string[]>(() => {
    const persisted = persistedChoice?.selected as string | undefined;
    if (persisted) return persisted.split(/[,、]/).map((s) => s.trim()).filter(Boolean);
    const stored = choiceStateStore.get(storeKey)?.selected;
    return stored ? stored.split(/[,、]/).map((s) => s.trim()).filter(Boolean) : [];
  });
  const [custom, setCustom] = useState("");
  const [sentCustom, setSentCustom] = useState(
    () =>
      (persistedChoice?.sentCustom as boolean | undefined) ??
      choiceStateStore.get(storeKey)?.sentCustom ??
      false
  );
  const [multiConfirmed, setMultiConfirmed] = useState(false);

  // 消息是异步加载的：首次渲染时 persistedChoice 可能还是空，
  // 加载完成后用它同步已选状态（覆盖初始 null），并写入模块级 store。
  // 用函数式 setState + 值守卫：persistedChoice 引用变化（如滚动引发的
  // 父组件重渲染）时，仅在实际值变化才触发重渲染，避免选项卡闪动。
  useEffect(() => {
    const persistedSelected = persistedChoice?.selected as string | undefined;
    const persistedSent = persistedChoice?.sentCustom as boolean | undefined;
    if (persistedSelected != null || persistedSent) {
      const nextSelected = persistedSelected ?? null;
      const nextSent = Boolean(persistedSent);
      const nextMulti = persistedSelected
        ? String(persistedSelected).split(/[,、]/).map((s) => s.trim()).filter(Boolean)
        : [];
      setSelected((prev) => (prev === nextSelected ? prev : nextSelected));
      setSentCustom((prev) => (prev === nextSent ? prev : nextSent));
      setSelectedMulti((prev) => {
        if (prev.length === nextMulti.length && prev.every((v, i) => v === nextMulti[i])) {
          return prev;
        }
        return nextMulti;
      });
      setMultiConfirmed((prev) => prev || nextMulti.length > 0);
      choiceStateStore.set(storeKey, {
        selected: nextSelected,
        sentCustom: nextSent,
        color_scheme: (persistedChoice?.color_scheme as string | undefined) ?? null,
      });
    }
  }, [persistedChoice, storeKey]);

  const options = useMemo(
    () =>
      (Array.isArray(data?.options) ? data.options : []).map((opt) =>
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
    pureblack: ["#000000", "#1A1A1A", "#9E9E9E", "#EBEBEB"],
    mistsage: ["#2A4540", "#8AB5B0", "#C8DDD9", "#3A5A56"],
    mistblue: ["#2A4858", "#8AA8C0", "#C8D8E4", "#3A5870"],
    duskmauve: ["#382A48", "#9A8AAB", "#CCC4D6", "#4A3A5C"],
    lotuspink: ["#4A342E", "#C4A098", "#DAC8C5", "#6A4A42"],
    dunesand: ["#403828", "#BCAE92", "#DCD4BE", "#5C5240"],
    smokegray: ["#343430", "#A8A7A0", "#D2D0CC", "#4A4945"],
  };

  const multiple = Boolean(data.multiple);

  const finished = multiple
    ? multiConfirmed
    : selected !== null || sentCustom;

  const persistChoice = (state: ChoiceState) => {
    choiceStateStore.set(storeKey, state);
    if (messageId) {
      void saveMessageChoiceState(messageId, {
        selected: state.selected,
        sentCustom: state.sentCustom,
        color_scheme: state.color_scheme ?? null,
      }).catch(() => {
        // 保存失败不阻塞交互；下次加载仍以模块级 store 为准
      });
    }
  };

  // 组装回传消息：选项 label + 副标题（不带卡片标题文案）
  const composeMsg = (opt: ChoiceOption) => {
    if (opt.color_scheme) {
      // 主题色卡片：保留「label（color_scheme）」机读格式让 Agent 明确传配色
      return `${opt.label}（${opt.color_scheme}）`;
    }
    return opt.desc ? `${opt.label}（${opt.desc}）` : opt.label;
  };

  // 单选：点击即发送选项
  const pick = (opt: ChoiceOption) => {
    if (finished) return;
    setSelected(opt.label);
    persistChoice({
      selected: opt.label,
      sentCustom: false,
      color_scheme: opt.color_scheme ?? null,
    });
    sendMessage(composeMsg(opt), [], effort);
  };

  // 多选：点击切换选中；确认后发送逗号分隔的 label 列表
  const toggleMulti = (label: string) => {
    if (finished) return;
    setSelectedMulti((prev) =>
      prev.includes(label)
        ? prev.filter((item) => item !== label)
        : [...prev, label]
    );
  };

  const confirmMulti = () => {
    if (finished || selectedMulti.length === 0) return;
    const msg = selectedMulti.join("、");
    setMultiConfirmed(true);
    persistChoice({
      selected: msg,
      sentCustom: false,
      color_scheme: null,
    });
    sendMessage(msg, [], effort);
  };

  const sendCustom = () => {
    const text = custom.trim();
    if (!text || finished) return;
    if (multiple) {
      // 多选：自定义项加入已选列表，由「确认选择」按钮统一发送（避免双按钮）
      setSelectedMulti((prev) =>
        prev.includes(text) ? prev : [...prev, text]
      );
      setCustom("");
      return;
    }
    setSentCustom(true);
    persistChoice({ selected: null, sentCustom: true, color_scheme: null });
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
          {options.map((opt) => {
            const active = multiple
              ? selectedMulti.includes(opt.label)
              : selected === opt.label;
            return (
              <Button
                key={opt.label}
                variant="secondary"
                size="medium"
                className={`choice-option${active ? " selected" : ""}${
                  multiple ? " multi" : ""
                }`}
                onClick={() =>
                  multiple ? toggleMulti(opt.label) : pick(opt)
                }
                disabled={finished}
              >
                <span className="choice-option-label">
                  {multiple && (
                    <Checkbox
                      checked={active}
                      onChange={() => toggleMulti(opt.label)}
                      size={14}
                      ariaLabel={opt.label}
                      className="choice-option-check"
                    />
                  )}
                  {opt.label}
                </span>
                {opt.desc && (
                  <span className="choice-option-desc">{opt.desc}</span>
                )}
              </Button>
            );
          })}
        </div>
      )}
      {multiple && (
        <div className="choice-confirm">
          <Button
            variant="primary"
            size="medium"
            className="choice-confirm-btn"
            onClick={confirmMulti}
            disabled={finished || selectedMulti.length === 0}
          >
            <Send size={13} />
            <span>
              {t("chat.choiceConfirm", "确认选择")}
              {selectedMulti.length > 0 ? `（${selectedMulti.length}）` : ""}
            </span>
          </Button>
        </div>
      )}
      {!multiple && data?.other && (
        <div className="choice-other">
          <Input
            className="choice-other-input"
            placeholder={t(
              "chat.choiceOtherPlaceholder",
              "其他选项，直接输入…"
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
    </div>
  );
}
