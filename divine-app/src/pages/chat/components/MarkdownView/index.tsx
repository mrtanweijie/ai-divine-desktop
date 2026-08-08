import { useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { isTauri, openUrl } from "@/services/tauri";

interface MarkdownViewProps {
  content: string;
  streaming: boolean;
}

export function MarkdownView({ content, streaming }: MarkdownViewProps) {
  return (
    <div className={`markdown-body ${streaming ? "streaming" : ""}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

function CodeBlock({ code, language }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };
  return (
    <div className="code-block">
      <div className="code-header">
        <span>{language || "code"}</span>
        <Button
          variant="icon"
          size="small"
          className="code-copy"
          onClick={copy}
          aria-label="复制代码"
          title="复制"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "已复制" : "复制"}
        </Button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

const components: Components = {
  code(props: any) {
    const { className, children, ...rest } = props;
    const language = /language-(\w+)/.exec(className || "")?.[1];
    const code = String(children ?? "").replace(/\n$/, "");
    if (!language && !code.includes("\n")) {
      return (
        <code className="inline-code" {...rest}>
          {code}
        </code>
      );
    }
    return <CodeBlock code={code} language={language} />;
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
