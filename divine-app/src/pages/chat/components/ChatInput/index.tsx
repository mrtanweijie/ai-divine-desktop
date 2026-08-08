import {
  ArrowUp,
  FileText,
  Paperclip,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";
import {
  forwardRef,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type MutableRefObject,
} from "react";
import type { ToolDefinition } from "@/types";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { Flex } from "@/components/ui/Flex";
import { TextArea } from "@/components/ui/TextArea";

interface ComposerProps {
  disabled: boolean;
  tools: ToolDefinition[];
  onSend: (question: string) => void;
}

export const ChatInput = forwardRef<HTMLTextAreaElement, ComposerProps>(
  function ChatInput(
    { disabled, tools, onSend },
    ref
  ) {
    const [value, setValue] = useState("");
    const [attached, setAttached] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const localRef = useRef<HTMLTextAreaElement>(
      null
    ) as MutableRefObject<HTMLTextAreaElement | null>;
    const textareaRef = localRef;

    const setRefs = (element: HTMLTextAreaElement | null) => {
      localRef.current = element;
      if (typeof ref === "function") {
        ref(element);
      } else if (ref) {
        (ref as MutableRefObject<HTMLTextAreaElement | null>).current = element;
      }
    };

    useEffect(() => {
      const element = textareaRef.current;
      if (!element) return;
      element.style.height = "auto";
      element.style.height = `${Math.min(element.scrollHeight, 240)}px`;
    }, [value, textareaRef]);

    const send = () => {
      const question = value.trim();
      if (!question || disabled) return;
      onSend(question);
      setValue("");
      setAttached(null);
    };

    const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;
      setAttached(file.name);
      try {
        const text = await file.text();
        const capped = text.slice(0, 8000);
        const prefix = `请阅读并处理以下附件「${file.name}」：\n\n`;
        setValue((prev) => `${prefix}\`\`\`\n${capped}\n\`\`\`\n\n${prev}`);
      } catch {
        setValue((prev) => `${prev}（附件 ${file.name} 无法读取）`);
      }
      if (fileInputRef.current) fileInputRef.current.value = "";
    };

    return (
      <div className="composer-wrap">
        <Flex direction="column" className="composer">
          <TextArea
            ref={setRefs}
            value={value}
            rows={1}
            placeholder="输入消息..."
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
            aria-label="输入消息"
          />
          {attached && (
            <Flex align="center" gap={6} className="attachment-chip">
              <FileText size={13} />
              <span>{attached}</span>
              <Button
                variant="icon"
                size="small"
                onClick={() => setAttached(null)}
                aria-label="移除附件"
              >
                <X size={12} />
              </Button>
            </Flex>
          )}
          <Flex
            align="center"
            justify="space-between"
            gap={8}
            className="composer-toolbar"
          >
            <Flex align="center" gap={4} className="composer-actions">
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,.json,.csv,.py"
                onChange={(event) => void handleFile(event)}
                hidden
              />
              <Button
                variant="icon"
                onClick={() => fileInputRef.current?.click()}
                title="附加文件"
                aria-label="附加文件"
              >
                <Paperclip size={16} />
              </Button>
              <Dropdown
                label="工具"
                align="start"
                items={tools.map((tool) => ({
                  key: tool.name,
                  label: tool.name,
                  description: tool.description,
                  icon: <Sparkles size={13} />,
                  onClick: () => {
                    setValue(toolPrompt(tool));
                    textareaRef.current?.focus();
                  },
                }))}
                trigger={
                  <Button variant="icon" title="工具" aria-label="工具">
                    <Wrench size={16} />
                  </Button>
                }
              />
            </Flex>
            <Button
              variant="primary"
              className="send-button"
              onClick={send}
              disabled={!value.trim() || disabled}
              aria-label="发送"
            >
              <ArrowUp size={16} />
            </Button>
          </Flex>
        </Flex>
        <p className="composer-hint">内容由 AI 生成，请核实重要信息</p>
      </div>
    );
  }
);

function toolPrompt(tool: ToolDefinition): string {
  if (tool.name === "word_document") {
    return "帮我生成一份 Word 文档，主题是项目周报";
  }
  if (tool.name === "spreadsheet") {
    return "帮我生成一份 Excel 表格，内容是项目进度";
  }
  if (tool.name === "notes") {
    return "帮我生成一份 Markdown 笔记，主题是 AI Workspace";
  }
  return `请使用 ${tool.name} 工具帮我完成一个任务`;
}
