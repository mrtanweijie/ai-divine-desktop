import { useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { toast } from "@/components/ui/Toast";
import { isTauri, openUrl } from "@/services/tauri";
import { copyText } from "@/utils";
import { HighlightedCode } from "./HighlightedCode";
import { languageLabel } from "./language";
import { MermaidBlock } from "./MermaidBlock";
import { WebPreviewBlock } from "./WebPreviewBlock";
import {
  ChoiceBlock,
  parseOptionsBlock,
} from "@/pages/chat/components/ChoiceBlock";

interface MarkdownViewProps {
  content: string;
  streaming: boolean;
}

export function MarkdownView({ content, streaming }: MarkdownViewProps) {
  return (
    <div className={`markdown-body ${streaming ? "streaming" : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={buildComponents(streaming)}
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

function buildComponents(streaming: boolean): Components {
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
      // 可点击选项卡片（如 PDF 风格选择）：流式时先显示源码，流结束后渲染按钮
      if (language === "options") {
        if (streaming) {
          return <CodeBlock code={code} language={language} streaming={streaming} />;
        }
        const data = parseOptionsBlock(code);
        return data ? (
          <ChoiceBlock data={data} />
        ) : (
          <CodeBlock code={code} language={language} streaming={streaming} />
        );
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
  };
}
