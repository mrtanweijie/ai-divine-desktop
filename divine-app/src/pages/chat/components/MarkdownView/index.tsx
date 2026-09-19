import { memo, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import type { ComponentProps } from "react";

type MdProps<K extends keyof Components> = ComponentProps<K> & {
  // react-markdown 会传入 hast 节点（本组件不使用）
  node?: unknown;
};
import remarkGfm from "remark-gfm";
import { Check, Copy, FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { toast } from "@/components/ui/Toast";
import { isTauri, openFileLocation, openFolder, openUrl } from "@/services/tauri";
import { copyText } from "@/utils";
import { API_BASE } from "@/services/request";
import { HighlightedCode } from "./HighlightedCode";
import { EMPTY_FENCE_SCAN, scanFences, unclosedFenceStart, type FenceScanState } from "./fenceScan";
import { languageLabel } from "./language";
import { MermaidBlock } from "./MermaidBlock";
import { WebPreviewBlock } from "./WebPreviewBlock";
import {
  ChoiceBlock,
  parseOptionsBlock,
  type ChoiceBlockData,
} from "@/pages/chat/components/ChoiceBlock";

/**
 * parseOptionsBlock 结果缓存。
 *
 * 代码块渲染器每次 react-markdown 重渲染都会执行（流式每 chunk 一次），
 * 而 ```options 块的内容在流式期间几乎每帧都在变——对同一份 code 反复跑
 * 「JSON.parse + 逐字符修复」是纯浪费。结果只取决于 code 串，缓存即可。
 * Map 保插入序做 FIFO 淘汰，避免长会话里无限增长。
 */
const optionsBlockCache = new Map<string, ChoiceBlockData | null>();
const OPTIONS_CACHE_MAX = 40;

function parseOptionsBlockCached(code: string): ChoiceBlockData | null {
  if (optionsBlockCache.has(code)) {
    return optionsBlockCache.get(code) ?? null;
  }
  const data = parseOptionsBlock(code);
  if (optionsBlockCache.size >= OPTIONS_CACHE_MAX) {
    const oldest = optionsBlockCache.keys().next().value;
    if (oldest !== undefined) optionsBlockCache.delete(oldest);
  }
  optionsBlockCache.set(code, data);
  return data;
}

/**
 * 把 Markdown 图片的 src 解析为可渲染的 URL：
 * - http(s)/data: 直接用
 * - 相对路径 / 绝对路径（如 images/xxx.png）→ 转成后端 /files/image 接口，
 *   由后端从 workspace / output 目录读取并返回图片。
 */
function resolveImageSrc(src?: string): string | null {
  if (!src) return null;
  if (/^(https?:\/\/|data:)/.test(src)) return src;
  // LLM 可能在 markdown 里输出 URL 编码过的路径（如 %E8%83%BD 代替中文），
  // 先解码回真实路径再统一编码，避免双重编码导致后端 404
  let decoded = src;
  try {
    decoded = decodeURIComponent(src);
  } catch {
    // 含非法转义序列（如字面 %）时保持原样
  }
  return `${API_BASE}/files/image?path=${encodeURIComponent(decoded)}`;
}

/**
 * 把 Markdown 文本里的绝对文件路径包成可点击链接（divine-path: 协议，
 * 由 a 渲染器拦截后调用 openFileLocation 在 Finder 中显示）。
 * 跳过 ``` 代码块，避免把代码里的路径也变成链接。
 * 两类匹配：
 *   - 带扩展名的路径（含空格/中文）：贪婪匹配到结尾扩展名
 *   - 目录路径（不含空格）：避免把后文散文吞进链接
 */
const ABS_PATH_RE =
  /(?<![\w\u4e00-\u9fff])(?:(?:\/|~\/|(?:[A-Za-z]:[\\/]))(?!\s)[^\n，。；、！？"'`<>|*?#[\]]{3,}\.\w{1,5}|(?:\/|~\/|(?:[A-Za-z]:[\\/]))(?!\s)[\w\-./\\（）()%+@,'_\u4e00-\u9fff]{3,}[\w)\u4e00-\u9fff])/g;

/** 严格判定是否像真实绝对路径，避免"A/B/C 列表"、"名词 / 域名"等误判。
 * 规则：~/ 开头（长度 >3）；盘符开头（长度 >4）；/ 开头且至少 2 段、
 * 首段 ≥2 字符（排除"选项 A/B/C"这类列表写法与根级单段）。 */
function looksLikeRealPath(path: string): boolean {
  if (path.startsWith("~/")) return path.length > 3;
  if (/^[A-Za-z]:[\\/]/.test(path)) return path.length > 4;
  if (!path.startsWith("/")) return false;
  const segments = path.slice(1).split(/[\\/]/).filter(Boolean);
  return segments.length >= 2 && segments[0].length >= 2;
}

function linkifyFilePaths(content: string): string {
  if (!content || content.length < 4) return content;
  // 保护代码块（```...```）与行内代码（`...`）：其中的路径不 linkify。
  // 模型常把路径包成行内代码（`/Users/...`），若在里面再包 divine-path
  // 链接，链接 markdown 会落在 <code> 里被当纯文本显示、不可点击。
  const protectedSpans: string[] = [];
  const masked = content.replace(/```[\s\S]*?```|`[^`\n]*`/g, (span) => {
    protectedSpans.push(span);
    return `\uE000${protectedSpans.length - 1}\uE000`;
  });
  const linkified = masked.replace(ABS_PATH_RE, (path) =>
    looksLikeRealPath(path) ? `[${path}](divine-path:${encodeURIComponent(path)})` : path,
  );
  return linkified.replace(/\uE000(\d+)\uE000/g, (_, index) => protectedSpans[Number(index)] ?? "");
}

interface MarkdownViewProps {
  content: string;
  streaming: boolean;
  messageId?: string;
  choiceState?: Record<string, unknown> | null;
}

/**
 * Markdown 渲染组件。
 *
 * 用 React.memo 阻断未变化消息的重渲染：流式更新时只有正在流式的
 * 那条消息 content 变化，其余历史消息的 content/messageId/choiceState
 * 引用都不变，浅比较即可跳过整棵 Markdown 解析树（react-markdown 的
 * markdown 解析 + linkifyFilePaths 全量正则 + 渲染器重建都是重活）。
 */
export const MarkdownView = memo(function MarkdownView({
  content,
  streaming,
  messageId,
  choiceState,
}: MarkdownViewProps) {
  const { t } = useTranslation();
  // buildComponents 每次渲染新建对象会破坏 react-markdown 内部按引用
  // 缓存 components 的机制 → 流式每 chunk 全量重解析。用 useMemo 固化，
  // 依赖变化时才重建（t 在语言切换时变化，此时重建是正确行为）。
  const components = useMemo(
    () => buildComponents(streaming, messageId, choiceState, t),
    [streaming, messageId, choiceState, t],
  );
  // linkifyFilePaths 对全文跑掩码→linkify→还原 3 遍正则，而流式每帧 content
  // 都在变 → 原先等于每帧全文重算。改为：流式期间不整段 linkify，冻结前缀交给
  // StableMarkdown 自己 linkify（它的 content 值不变，memo 后只算一次），活动
  // 尾块留到流结束后统一 linkify。代价是流式期间尾块里的路径暂为纯文本、流结束
  // 后变可点击；已冻结的前缀不受影响。
  const linkified = useMemo(
    () => (streaming ? content : linkifyFilePaths(content)),
    [content, streaming],
  );
  // 已闭合块冻结（流式渲染优化）：流式期间若存在未闭合代码围栏，把内容
  // 拆成「冻结前缀 + 活动围栏块」——前缀引用不变，memo 后每帧只重解析
  // 围栏内的活动块（长代码块流式的 O(n²) 重解析大头）。非流式与无未闭合
  // 围栏时保持整段渲染，完成态与历史消息不受影响。
  // 围栏扫描是增量的（scanFences 只扫新增行），不再每帧 split 全文。
  // 状态用 useState 而非 useRef：渲染期间读写 ref 会被 react-hooks/refs 拦下，
  // 而「渲染期间派生状态」正是 React 官方推荐写法——值没变时 nextFenceScan
  // 就是同一个对象引用，setState 不会触发额外渲染。
  const [fenceScan, setFenceScan] = useState<FenceScanState>(EMPTY_FENCE_SCAN);
  const nextFenceScan = streaming ? scanFences(fenceScan, content) : fenceScan;
  if (nextFenceScan !== fenceScan) setFenceScan(nextFenceScan);
  const splitIndex = streaming ? unclosedFenceStart(nextFenceScan, content) : -1;
  const stablePart = splitIndex > 0 ? content.slice(0, splitIndex) : null;
  const tailPart = splitIndex > 0 ? content.slice(splitIndex) : null;
  return (
    <div className={`markdown-body ${streaming ? "streaming" : ""}`}>
      {stablePart !== null ? (
        <>
          <StableMarkdown content={stablePart} components={components} />
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            urlTransform={(url) => url}
            components={components}
          >
            {tailPart}
          </ReactMarkdown>
        </>
      ) : (
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          // react-markdown 默认 urlTransform 会过滤非 http/https 协议，
          // 导致 divine-path: 链接的 href 被替换为空串、点击失效。
          // 这里放行原样保留 URL；点击行为由下方 a 渲染器拦截（仅处理
          // http(s) 与 divine-path:）。
          urlTransform={(url) => url}
          components={components}
        >
          {linkified}
        </ReactMarkdown>
      )}
    </div>
  );
});

/** 冻结前缀渲染器：content 引用不变时 memo 直接跳过整段重解析。 */
const StableMarkdown = memo(function StableMarkdown({
  content,
  components,
}: {
  content: string;
  components: Components;
}) {
  const linkified = useMemo(() => linkifyFilePaths(content), [content]);
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={(url) => url} components={components}>
      {linkified}
    </ReactMarkdown>
  );
});

function extractText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (typeof node === "object" && "props" in node) {
    const element = node as { props?: { children?: ReactNode } };
    return extractText(element.props?.children);
  }
  return "";
}

function CodeBlock({
  code,
  language,
  streaming,
}: {
  code: string;
  language?: string;
  streaming: boolean;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await copyText(code);
    setCopied(true);
    toast.success(t("markdown.copied", "代码已复制"));
    setTimeout(() => setCopied(false), 1200);
  };
  return (
    <div className="code-block">
      <div className="code-header">
        <span>{languageLabel(language)}</span>
        <Button
          variant="icon"
          size="small"
          className="code-copy"
          onClick={copy}
          aria-label={t("markdown.copyCode", "复制代码")}
          title={copied ? t("common.copied", "已复制") : t("markdown.copy", "复制")}
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </Button>
      </div>
      <pre className="code-pre">
        <HighlightedCode code={code} language={language} streaming={streaming} />
      </pre>
    </div>
  );
}

function buildComponents(
  streaming: boolean,
  messageId?: string,
  choiceState?: Record<string, unknown> | null,
  t?: (key: string, options?: Record<string, unknown>) => string,
): Components {
  return {
    code(props: MdProps<"code">) {
      const { className, children, ...rest } = props;
      const language = /language-([^\s]+)/i.exec(className || "")?.[1]?.toLowerCase();
      const code = extractText(children).replace(/\n$/, "");
      if (!language && !code.includes("\n")) {
        return (
          <code className="inline-code" {...rest}>
            {children}
          </code>
        );
      }
      if (language === "mermaid" || language === "mmd") {
        return <MermaidBlock code={code} streaming={streaming} />;
      }
      // 可点击选项卡片（如 PDF 风格选择）：流式时不显示 JSON 源码；
      // options 块一旦闭合（JSON 可解析）就立即渲染成卡片，不必等整条消息流结束；
      // 未闭合（流式中途）时隐藏，避免闪出源码文本
      if (language === "options") {
        const data = parseOptionsBlockCached(code);
        if (data) {
          return <ChoiceBlock data={data} messageId={messageId} persistedChoice={choiceState} />;
        }
        if (streaming) {
          return null;
        }
        return <CodeBlock code={code} language={language} streaming={streaming} />;
      }
      if (language === "svg") {
        // SVG 流式中途就进预览（浏览器可渲染未闭合的半截 SVG），边画边看；
        // WebPreviewBlock 内部对 srcDoc 做 250ms 节流，避免每个 token 整页重载
        return (
          <WebPreviewBlock code={code} language="svg" defaultMode="preview" streaming={streaming} />
        );
      }
      if ((language === "html" || language === "htm") && !streaming) {
        return (
          <WebPreviewBlock
            code={code}
            language="html"
            // HTML 保持默认源码且流式结束后才渲染——聊天里的多为片段，
            // 半截 HTML 直接渲染易闪白/布局突兀
            defaultMode="source"
          />
        );
      }
      return <CodeBlock code={code} language={language} streaming={streaming} />;
    },
    table(props: MdProps<"table">) {
      const { children, ...rest } = props;
      return (
        <div className="markdown-table-wrap">
          <table {...rest}>{children}</table>
        </div>
      );
    },
    p(props: MdProps<"p">) {
      const { children, ...rest } = props;
      const text = extractText(children).trim();
      // 检测裸 JSON（LLM 未用 ```options 包裹的情况）：以 { 开头、含 "options" 数组
      if (text.startsWith("{") && text.includes('"options"')) {
        const data = parseOptionsBlockCached(text);
        if (data) {
          return <ChoiceBlock data={data} messageId={messageId} persistedChoice={choiceState} />;
        }
      }
      return <p {...rest}>{children}</p>;
    },
    a(props: MdProps<"a">) {
      const href = props.href as string | undefined;
      // 本地文件路径链接：目录直接打开文件夹；文件则在其所在文件夹中显示
      if (href?.startsWith("divine-path:")) {
        const path = decodeURIComponent(href.slice("divine-path:".length));
        return (
          <a
            href="#"
            className="file-path-link"
            title={t?.("chat.openFileLocation", { defaultValue: "打开所在目录" }) ?? "打开所在目录"}
            onClick={(event) => {
              event.preventDefault();
              if (isTauri()) {
                void openFolder(path).catch(() => {
                  void openFileLocation(path);
                });
              }
            }}
          >
            <FolderOpen size={12} />
            <span>{props.children}</span>
          </a>
        );
      }
      return (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          onClick={(event) => {
            if (href && /^https?:\/\//.test(href) && isTauri()) {
              event.preventDefault();
              void openUrl(href);
            }
          }}
        >
          {props.children}
        </a>
      );
    },
    img(props: MdProps<"img">) {
      const { src, alt, ...rest } = props;
      const resolved = resolveImageSrc(src);
      if (!resolved) return null;
      return (
        <img
          src={resolved}
          alt={alt || ""}
          className="markdown-image"
          loading="eager"
          // 加载失败时隐藏而不是显示裂图，避免页面反复闪烁
          onError={(event) => {
            const element = event.currentTarget;
            element.style.display = "none";
          }}
          {...rest}
        />
      );
    },
  };
}
