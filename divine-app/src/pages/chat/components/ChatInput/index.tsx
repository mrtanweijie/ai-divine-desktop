import {
  ArrowUp,
  FileText,
  Paperclip,
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
import { open } from "@tauri-apps/plugin-dialog";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { TextArea } from "@/components/ui/TextArea";
import type { ChatFile } from "@/types";
import { isTauri } from "@/services/tauri";

interface ComposerProps {
  disabled: boolean;
  onSend: (question: string, files: ChatFile[]) => void;
}

export const ChatInput = forwardRef<HTMLTextAreaElement, ComposerProps>(
  function ChatInput(
    { disabled, onSend },
    ref
  ) {
    const [value, setValue] = useState("");
    const [attached, setAttached] = useState<ChatFile | null>(null);
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
      const files: ChatFile[] = attached ? [attached] : [];
      onSend(question, files);
      setValue("");
      setAttached(null);
    };

    const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;
      let content = "";
      try {
        content = (await file.text()).slice(0, 10000);
      } catch {
        content = "";
      }
      setAttached({ name: file.name, size: file.size, content });
      if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const pickAttachment = async () => {
      if (isTauri()) {
        const selected = await open({ multiple: false });
        if (typeof selected === "string") {
          const name = selected.split(/[\\/]/).pop() || selected;
          setAttached({ name, path: selected });
        }
        return;
      }
      fileInputRef.current?.click();
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
              <span>{attached.name}</span>
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
                accept=".txt,.md,.json,.csv,.py,.png,.jpg,.jpeg,.webp,.gif,.bmp"
                onChange={(event) => void handleFile(event)}
                hidden
              />
              <Button
                variant="icon"
                onClick={() => void pickAttachment()}
                title="附加文件"
                aria-label="附加文件"
              >
                <Paperclip size={16} />
              </Button>
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
