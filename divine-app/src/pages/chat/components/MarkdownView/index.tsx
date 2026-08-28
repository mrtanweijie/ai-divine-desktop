import { useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { toast } from "@/components/ui/Toast";
import { isTauri, openFileLocation, openFolder, openUrl } from "@/services/tauri";
import { copyText } from "@/utils";
import { API_BASE } from "@/services/request";
import { HighlightedCode } from "./HighlightedCode";
import { languageLabel } from "./language";
import { MermaidBlock } from "./MermaidBlock";
import { WebPreviewBlock } from "./WebPreviewBlock";
import {
  ChoiceBlock,
  parseOptionsBlock,
} from "@/pages/chat/components/ChoiceBlock";

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
  /(?<![\w])(?:(?:\/|~\/|(?:[A-Za-z]:[\\/]))[^\n，。；、！？"'`<>|*?#[\]]{3,}\.\w{1,5}|(?:\/|~\/|(?:[A-Za-z]:[\\/]))[\w\-./\\（）()%+@,'_\u4e00-\u9fff]{3,}[\w)\u4e00-\u9fff])/g;

function linkifyFilePaths(content: string): string {
  if (!content || content.length < 4) return content;
  const parts = content.split("```");
  return parts
    .map((part, index) => {
      // 奇数下标是代码块内容，不处理
      if (index % 2 === 1) return part;
      return part.replace(
        ABS_PATH_RE,
        (path) => `[${path}](divine-path:${encodeURIComponent(path)})`
      );
    })
    .join("```");
}

interface MarkdownViewProps {
  content: string;
  streaming: boolean;
  messageId?: string;
  choiceState?: Record<string, unknown> | null;
}

export function MarkdownView({
  content,
  streaming,
  messageId,
  choiceState,
}: MarkdownViewProps) {
  const { t } = useTranslation();
  return (
    <div className={`markdown-body ${streaming ? "streaming" : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={buildComponents(streaming, messageId, choiceState, t)}
      >
        {linkifyFilePaths(content)}
      </ReactMarkdown>
    </div>
  );
}

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
          title={
            copied ? t("common.copied", "已复制") : t("markdown.copy", "复制")
          }
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </Button>
      </div>
      <pre className="code-pre">
        <HighlightedCode
          code={code}
          language={language}
          streaming={streaming}
        />
      </pre>
    </div>
  );
}

function buildComponents(
  streaming: boolean,
  messageId?: string,
  choiceState?: Record<string, unknown> | null,
  t?: (key: string, options?: Record<string, unknown>) => string
): Components {
  return {
    code(props: any) {
      const { className, children, ...rest } = props;
      const language = /language-([^\s]+)/i
        .exec(className || "")?.[1]
        ?.toLowerCase();
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
        const data = parseOptionsBlock(code);
        if (data) {
          return (
            <ChoiceBlock
              data={data}
              messageId={messageId}
              persistedChoice={choiceState}
            />
          );
        }
        if (streaming) {
          return null;
        }
        return <CodeBlock code={code} language={language} streaming={streaming} />;
      }
      if (
        (language === "html" || language === "htm" || language === "svg") &&
        !streaming
      ) {
        return (
          <WebPreviewBlock
            code={code}
            language={language === "svg" ? "svg" : "html"}
          />
        );
      }
      return (
        <CodeBlock code={code} language={language} streaming={streaming} />
      );
    },
    table(props: any) {
      const { children, ...rest } = props;
      return (
        <div className="markdown-table-wrap">
          <table {...rest}>{children}</table>
        </div>
      );
    },
    a(props: any) {
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
    img(props: any) {
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
