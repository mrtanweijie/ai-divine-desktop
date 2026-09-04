import { useEffect, useId, useRef, useState } from "react";
import type { MermaidConfig } from "mermaid";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import { toast } from "@/components/ui/Toast";
import { UI_COLORS } from "@/styles/uiPalette";
import { copyText } from "@/utils";

type MermaidApi = (typeof import("mermaid"))["default"];
type RenderStatus = "loading" | "ready" | "error";

const SVG_CACHE_LIMIT = 30;
const svgCache = new Map<
  string,
  {
    id: string;
    svg: string;
  }
>();

let mermaidPromise: Promise<MermaidApi> | null = null;

const FONT_STACK =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif';

const DARK_THEME_VARIABLES = {
  primaryColor: UI_COLORS.dark.surface2,
  primaryTextColor: UI_COLORS.dark.text,
  primaryBorderColor: "#3f4a56",
  lineColor: "#7c8794",
  fontSize: "12px",
  titleFontSize: "14px",
  secondaryColor: UI_COLORS.dark.surface,
  tertiaryColor: UI_COLORS.dark.codeBg,
  clusterBkg: UI_COLORS.dark.surface,
  clusterBorder: "#3f4a56",
  edgeLabelBackground: UI_COLORS.dark.surface,
  nodeTextColor: UI_COLORS.dark.text,
  fontFamily: FONT_STACK,
  nodeBorderRadius: "8px",
};

const LIGHT_THEME_VARIABLES = {
  primaryColor: UI_COLORS.light.surface,
  primaryTextColor: UI_COLORS.light.text,
  primaryBorderColor: "#cbd5e1",
  lineColor: "#64748b",
  fontSize: "12px",
  titleFontSize: "14px",
  secondaryColor: UI_COLORS.light.surface2,
  tertiaryColor: UI_COLORS.light.codeBg,
  clusterBkg: UI_COLORS.light.surface2,
  clusterBorder: "#cbd5e1",
  edgeLabelBackground: UI_COLORS.light.surface,
  nodeTextColor: UI_COLORS.light.text,
  fontFamily: FONT_STACK,
  nodeBorderRadius: "8px",
};

function currentTheme(): "dark" | "light" {
  return document.documentElement.dataset.theme === "light"
    ? "light"
    : "dark";
}

function mermaidConfig(theme: "dark" | "light"): MermaidConfig {
  return {
    startOnLoad: false,
    securityLevel: "strict",
    theme: "base",
    fontFamily: FONT_STACK,
    fontSize: 12,
    maxTextSize: 20000,
    themeVariables:
      theme === "light" ? LIGHT_THEME_VARIABLES : DARK_THEME_VARIABLES,
    flowchart: {
      htmlLabels: false,
      curve: "basis",
      padding: 8,
      nodeSpacing: 32,
      rankSpacing: 32,
      wrappingWidth: 150,
      diagramPadding: 8,
    },
  };
}

async function loadMermaid(): Promise<MermaidApi> {
  mermaidPromise ??= import("mermaid").then((module) => module.default);
  return mermaidPromise;
}

function cacheKey(theme: "dark" | "light", code: string): string {
  return `${theme}\u0000${code}`;
}

function rememberSvg(
  key: string,
  entry: { id: string; svg: string }
): void {
  if (svgCache.size >= SVG_CACHE_LIMIT) {
    const oldest = svgCache.keys().next().value;
    if (oldest) svgCache.delete(oldest);
  }
  svgCache.set(key, entry);
}

function useThemeVersion(): "dark" | "light" {
  const [theme, setTheme] = useState(currentTheme);

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setTheme(currentTheme());
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  return theme;
}

function normalizeMermaidSource(code: string): string {
  return code
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/\\"/g, '"')
    .replace(/\\'/g, "'");
}

/** 显式 style 的 fill 与主题默认文字对比冲突时的兜底文字色 */
const AUTO_CONTRAST_TEXT = {
  dark: UI_COLORS.light.text, // 浅色底 -> 补深色字（#1f2937）
  light: UI_COLORS.dark.text, // 深色底 -> 补浅色字（#f2f4f6）
} as const;

function hexLuma(hex: string): number {
  let h = hex.replace("#", "");
  if (h.length === 3) {
    h = h
      .split("")
      .map((c) => c + c)
      .join("");
  }
  const value = parseInt(h.slice(0, 6), 16);
  if (Number.isNaN(value)) return 0;
  const r = ((value >> 16) & 0xff) / 255;
  const g = ((value >> 8) & 0xff) / 255;
  const b = (value & 0xff) / 255;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * 深色模式下，图表里常见的 `style X fill:#c6e0b4`（作者按浅底习惯写的浅色块，
 * 却不写 color）会让文字沿用主题的浅白色，浅底白字不可读。
 * 这里对未显式写 color 的 style 行按 fill 亮度自动补对比文字色：
 * 亮底补深字（dark 主题）、暗底补浅字（light 主题），与主题默认文字方向相反才注入。
 */
function ensureContrastingText(code: string, theme: "dark" | "light"): string {
  const force =
    theme === "dark"
      ? { above: true, color: AUTO_CONTRAST_TEXT.dark }
      : { above: false, color: AUTO_CONTRAST_TEXT.light };
  return code.replace(
    /^(\s*style\s+)([^;\n]*?)(\s*;?\s*)$/gm,
    (whole, head: string, body: string, tail: string) => {
      if (/\bcolor\s*:/i.test(body)) return whole;
      const fill = body.match(/(?:^|[, ])fill\s*:\s*(#[0-9a-fA-F]{3,8})/i);
      if (!fill) return whole;
      const isLight = hexLuma(fill[1]) >= 0.5;
      if (isLight !== force.above) return whole;
      const trimmed = body.replace(/,\s*$/, "").replace(/\s+$/, "");
      return `${head}${trimmed},color:${force.color}${tail}`;
    }
  );
}

interface MermaidBlockProps {
  code: string;
  streaming: boolean;
}

export function MermaidBlock({ code, streaming }: MermaidBlockProps) {
  const { t } = useTranslation();
  const theme = useThemeVersion();
  const normalizedCode = normalizeMermaidSource(code);
  const baseId = useId().replace(/[^a-zA-Z0-9]/g, "");
  const instanceId = `mermaid-${baseId}`;
  const key = cacheKey(theme, normalizedCode);
  const cached = svgCache.get(key);
  const [status, setStatus] = useState<RenderStatus>(
    cached ? "ready" : "loading"
  );
  const [svg, setSvg] = useState(
    cached ? replaceSvgId(cached.svg, cached.id, instanceId) : ""
  );
  const [copied, setCopied] = useState(false);
  const renderSeq = useRef(0);

  useEffect(() => {
    if (streaming) {
      return;
    }
    const cachedSvg = svgCache.get(cacheKey(theme, normalizedCode));
    if (cachedSvg) {
      setSvg(replaceSvgId(cachedSvg.svg, cachedSvg.id, instanceId));
      setStatus("ready");
      return;
    }
    const seq = renderSeq.current + 1;
    renderSeq.current = seq;
    let cancelled = false;
    setStatus("loading");
    setSvg("");

    void loadMermaid()
      .then((mermaid) => {
        if (cancelled) return null;
        mermaid.initialize(mermaidConfig(theme));
        return mermaid.render(
          `${instanceId}-${seq}`,
          ensureContrastingText(normalizedCode, theme)
        );
      })
      .then((result) => {
        if (cancelled || !result || seq !== renderSeq.current) return;
        rememberSvg(cacheKey(theme, normalizedCode), {
          id: `${instanceId}-${seq}`,
          svg: result.svg,
        });
        setSvg(result.svg);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled && seq === renderSeq.current) {
          setStatus("error");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [normalizedCode, instanceId, streaming, theme]);

  function replaceSvgId(source: string, fromId: string, toId: string): string {
    return fromId === toId ? source : source.split(fromId).join(toId);
  }

  const copy = async () => {
    await copyText(normalizedCode);
    setCopied(true);
    toast.success(t("mermaid.copiedSource", "Mermaid 源码已复制"));
    setTimeout(() => setCopied(false), 1200);
  };

  return (
    <div className={`mermaid-block ${status}`}>
      <div className="mermaid-header">
        <span>
          {status === "error"
            ? t("mermaid.parseFailed", "Mermaid 解析失败")
            : "Mermaid"}
        </span>
        <Button
          variant="icon"
          size="small"
          className="mermaid-copy"
          onClick={copy}
          aria-label={t("mermaid.copySource", "复制 Mermaid 源码")}
          title={
            copied
              ? t("common.copied", "已复制")
              : t("mermaid.copyCode", "复制源码")
          }
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </Button>
      </div>
      {streaming ? (
        <pre className="mermaid-source">{normalizedCode}</pre>
      ) : status === "ready" && svg ? (
        <div
          className="mermaid-canvas"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : status === "error" ? (
        <pre className="mermaid-source">{normalizedCode}</pre>
      ) : (
        <div className="mermaid-loading">
          <LoadingOrb state="working" size={20} speed={3} />
          <span>{t("mermaid.rendering", "渲染中")}</span>
        </div>
      )}
    </div>
  );
}
