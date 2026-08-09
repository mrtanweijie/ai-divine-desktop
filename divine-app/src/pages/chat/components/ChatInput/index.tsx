import {
  ArrowUp,
  ChevronDown,
  FileText,
  Plus,
  ShieldCheck,
  X,
} from "lucide-react";
import {
  forwardRef,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type MutableRefObject,
  type ReactNode,
} from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { Flex } from "@/components/ui/Flex";
import { TextArea } from "@/components/ui/TextArea";
import type { ApprovalMode, ChatFile } from "@/types";
import { isTauri } from "@/services/tauri";

const APPROVAL_MODE_LABELS: Record<ApprovalMode, string> = {
  ask: "请求批准",
  assist: "帮我批准",
  full: "完全访问权限",
};

const APPROVAL_MODE_ITEMS: {
  key: ApprovalMode;
  label: string;
  description: string;
}[] = [
  {
    key: "ask",
    label: "请求批准",
    description: "编辑外部文件和使用互联网时始终询问",
  },
  {
    key: "assist",
    label: "帮我批准",
    description: "仅检测到危险操作请求批准",
  },
  {
    key: "full",
    label: "完全访问权限",
    description: "可不受限制地访问互联网和您电脑上的任何文件",
  },
];

interface ComposerProps {
  disabled: boolean;
  onSend: (question: string, files: ChatFile[]) => void;
  approvalMode: ApprovalMode;
  onApprovalModeChange: (mode: ApprovalMode) => void;
  prefill?: { text: string; nonce: number } | null;
  onPrefillConsumed: () => void;
  projectPicker?: ReactNode;
}

export const ChatInput = forwardRef<HTMLTextAreaElement, ComposerProps>(
  function ChatInput(
    {
      disabled,
      onSend,
      approvalMode,
      onApprovalModeChange,
      prefill,
      onPrefillConsumed,
      projectPicker,
    },
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

    useEffect(() => {
      if (!prefill) return;
      setValue(prefill.text);
      onPrefillConsumed();
      textareaRef.current?.focus();
    }, [onPrefillConsumed, prefill]);

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
        {projectPicker}
        <Flex direction="column" className="composer">
          <TextArea
            ref={setRefs}
            value={value}
            rows={1}
            placeholder="随心输入"
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
              <div
                className="attachment-trigger"
                role="button"
                tabIndex={0}
                title="附加文件"
                aria-label="附加文件"
                onClick={() => void pickAttachment()}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    void pickAttachment();
                    event.currentTarget.blur();
                  }
                }}
              >
                <Plus size={16} />
              </div>
              <Dropdown
                align="start"
                direction="above"
                label="审批模式"
                trigger={
                  <Button
                    variant="ghost"
                    size="small"
                    className="approval-mode-trigger"
                    title="审批模式"
                  >
                    <ShieldCheck size={14} />
                    <span>{APPROVAL_MODE_LABELS[approvalMode]}</span>
                    <ChevronDown size={12} />
                  </Button>
                }
                items={APPROVAL_MODE_ITEMS.map((item) => ({
                  key: item.key,
                  label: item.label,
                  description: item.description,
                  onClick: () => onApprovalModeChange(item.key),
                }))}
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
