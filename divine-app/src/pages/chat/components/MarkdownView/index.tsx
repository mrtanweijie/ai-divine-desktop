import { useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { toast } from "@/components/ui/Toast";
import { isTauri, openUrl } from "@/services/tauri";
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
  return (
    <div className={`markdown-body ${streaming ? "streaming" : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={buildComponents(streaming, messageId, choiceState)}
      >
        {content}
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
  choiceState?: Record<string, unknown> | null
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
      return (
        <a
          href={props.href}
          target="_blank"
          rel="noreferrer"
          onClick={(event) => {
            const href = props.href as string | undefined;
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
