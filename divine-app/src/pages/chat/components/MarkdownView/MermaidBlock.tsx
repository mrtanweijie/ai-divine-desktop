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
        return mermaid.render(`${instanceId}-${seq}`, normalizedCode);
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
