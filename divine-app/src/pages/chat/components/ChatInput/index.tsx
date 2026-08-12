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
import type { ApprovalMode, ChatFile, PreviewFile } from "@/types";
import { isTauri, savePasteText } from "@/services/tauri";
import { formatSize } from "@/utils";

const PASTE_AS_FILE_CHAR_THRESHOLD = 2000;
const PASTE_AS_FILE_LINE_THRESHOLD = 500;

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
  onPreviewFile?: (file: PreviewFile) => void;
  onValueChange?: (hasValue: boolean) => void;
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
      onPreviewFile,
      onValueChange,
      approvalMode,
      onApprovalModeChange,
      prefill,
      onPrefillConsumed,
      projectPicker,
    },
    ref
  ) {
    const [value, setValue] = useState("");
    const [attached, setAttached] = useState<ChatFile[]>([]);
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
      const next = prefill.text;
      setValue(next);
      onValueChange?.(next.trim().length > 0);
      onPrefillConsumed();
      textareaRef.current?.focus();
    }, [onPrefillConsumed, onValueChange, prefill]);

    const send = () => {
      const question = value.trim();
      if (!question || disabled) return;
      onSend(question, attached);
      setValue("");
      setAttached([]);
    };

    const attachmentKey = (file: ChatFile) =>
      `${file.name}-${file.path ?? file.content?.slice(0, 8) ?? ""}`;

    const removeAttachment = (file: ChatFile) => {
      const key = attachmentKey(file);
      setAttached((prev) => prev.filter((item) => attachmentKey(item) !== key));
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
      setAttached((prev) => [
        ...prev,
        { name: file.name, size: file.size, content },
      ]);
      if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const handlePaste = async (
      event: React.ClipboardEvent<HTMLTextAreaElement>
    ) => {
      const native = event.nativeEvent as ClipboardEvent & {
        ctrlKey?: boolean;
        metaKey?: boolean;
        shiftKey?: boolean;
      };
      if (native.ctrlKey && native.shiftKey) return;
      if (native.metaKey && native.shiftKey) return;
      const text = event.clipboardData?.getData("text/plain") || "";
      const lineCount = text.split(/\r?\n/).length;
      const tooLarge =
        text.length >= PASTE_AS_FILE_CHAR_THRESHOLD ||
        lineCount >= PASTE_AS_FILE_LINE_THRESHOLD;
      if (!text || !tooLarge) return;

      event.preventDefault();
      try {
        const saved = await savePasteText(text);
        setAttached((prev) => [
          ...prev,
          { name: saved.name, path: saved.path, size: saved.size },
        ]);
      } catch {
        setValue((prev) => (prev ? `${prev}\n${text}` : text));
        onValueChange?.(true);
        textareaRef.current?.focus();
      }
    };

    const pickAttachment = async () => {
      if (isTauri()) {
        const selected = await open({ multiple: false });
        if (typeof selected === "string") {
          const name = selected.split(/[\\/]/).pop() || selected;
          setAttached((prev) => [...prev, { name, path: selected }]);
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
            onChange={(event) => {
              const next = event.target.value;
              setValue(next);
              onValueChange?.(next.trim().length > 0);
            }}
            onPaste={(event) => void handlePaste(event)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
            aria-label="输入消息"
          />
          {attached.length > 0 && (
            <Flex direction="column" gap={6} className="attachment-chips">
              {attached.map((file) => (
                <Flex
                  key={attachmentKey(file)}
                  align="center"
                  gap={6}
                  className="attachment-chip"
                >
                  <FileText size={13} />
                  <span
                    className={
                      file.path && onPreviewFile
                        ? "attachment-name attachment-name-preview"
                        : "attachment-name"
                    }
                    role={file.path && onPreviewFile ? "button" : undefined}
                    tabIndex={file.path && onPreviewFile ? 0 : undefined}
                    title={file.path && onPreviewFile ? "预览" : undefined}
                    onClick={
                      file.path && onPreviewFile
                        ? () =>
                            onPreviewFile({
                              repoPath: "",
                              relPath: file.name,
                              fileName: file.name,
                              path: file.path,
                            })
                        : undefined
                    }
                    onKeyDown={
                      file.path && onPreviewFile
                        ? (event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              onPreviewFile({
                                repoPath: "",
                                relPath: file.name,
                                fileName: file.name,
                                path: file.path,
                              });
                            }
                          }
                        : undefined
                    }
                  >
                    {file.name}
                  </span>
                  {file.size != null && (
                    <span className="attachment-size">{formatSize(file.size)}</span>
                  )}
                  <Button
                    variant="icon"
                    size="small"
                    onClick={() => removeAttachment(file)}
                    aria-label={`移除附件 ${file.name}`}
                  >
                    <X size={12} />
                  </Button>
                </Flex>
              ))}
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
