import {
  ArrowUp,
  ChevronDown,
  FileText,
  Plus,
  ShieldCheck,
  Square,
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
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { Flex } from "@/components/ui/Flex";
import { TextArea } from "@/components/ui/TextArea";
import type { ApprovalMode, ChatFile, PreviewFile } from "@/types";
import { isTauri, savePasteText } from "@/services/tauri";
import { formatSize } from "@/utils";

const PASTE_AS_FILE_CHAR_THRESHOLD = 2000;
const PASTE_AS_FILE_LINE_THRESHOLD = 500;

interface ComposerProps {
  disabled: boolean;
  onSend: (question: string, files: ChatFile[]) => void;
  onStop?: () => void;
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
      onStop,
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
    const { t } = useTranslation();
    const approvalModeLabels: Record<ApprovalMode, string> = {
      ask: t("chat.approvalAsk", "请求批准"),
      assist: t("chat.approvalAssist", "帮我批准"),
      full: t("chat.approvalFull", "完全访问权限"),
    };
    const approvalModeItems = [
      {
        key: "ask" as const,
        label: t("chat.approvalAsk", "请求批准"),
        description: t(
          "chat.approvalAskDescription",
          "编辑外部文件和使用互联网时始终询问"
        ),
      },
      {
        key: "assist" as const,
        label: t("chat.approvalAssist", "帮我批准"),
        description: t(
          "chat.approvalAssistDescription",
          "仅检测到危险操作请求批准"
        ),
      },
      {
        key: "full" as const,
        label: t("chat.approvalFull", "完全访问权限"),
        description: t(
          "chat.approvalFullDescription",
          "可不受限制地访问互联网和您电脑上的任何文件"
        ),
      },
    ];
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
      if ((!question && attached.length === 0) || disabled) return;
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
            placeholder={t("chat.inputPlaceholder", "随心输入")}
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
            aria-label={t("chat.inputLabel", "输入消息")}
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
                    title={
                      file.path && onPreviewFile
                        ? t("chat.preview", "预览")
                        : undefined
                    }
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
                    aria-label={t("chat.removeAttachment", "移除附件 {{name}}", {
                      name: file.name,
                    })}
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
                title={t("chat.attachFile", "附加文件")}
                aria-label={t("chat.attachFile", "附加文件")}
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
                label={t("chat.approvalMode", "审批模式")}
                openOn="click"
                trigger={
                  <Button
                    variant="ghost"
                    size="small"
                    className="approval-mode-trigger"
                    title={t("chat.approvalMode", "审批模式")}
                  >
                    <ShieldCheck size={14} />
                    <span>{approvalModeLabels[approvalMode]}</span>
                    <ChevronDown size={12} />
                  </Button>
                }
                items={approvalModeItems.map((item) => ({
                  key: item.key,
                  label: item.label,
                  description: item.description,
                  onClick: () => onApprovalModeChange(item.key),
                }))}
              />
            </Flex>
            {disabled && onStop ? (
              <Button
                variant="secondary"
                className="send-button stop-button"
                onClick={onStop}
                aria-label={t("chat.stop", "停止生成")}
                title={t("chat.stop", "停止生成")}
              >
                <Square size={16} />
              </Button>
            ) : (
              <Button
                variant="primary"
                className="send-button"
                onClick={send}
                disabled={(!value.trim() && attached.length === 0) || disabled}
                aria-label={t("chat.send", "发送")}
              >
                <ArrowUp size={16} />
              </Button>
            )}
          </Flex>
        </Flex>
        <p className="composer-hint">
          {t("chat.aiDisclaimer", "内容由 AI 生成，请核实重要信息")}
        </p>
      </div>
    );
  }
);
