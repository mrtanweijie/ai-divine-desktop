import { ArrowUp, ChevronDown, Plus, ShieldCheck, Square, X } from "lucide-react";
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
import { isComposingEvent } from "@/config/keymap";
import { Button } from "@/components/ui/Button";
import { Dropdown } from "@/components/ui/Dropdown";
import { FileTypeIcon } from "@/components/FileTypeIcon";
import { Flex } from "@/components/ui/Flex";
import { TextArea } from "@/components/ui/TextArea";
import type {
  ApprovalMode,
  ChatFile,
  MentionCandidate,
  MentionKind,
  MentionRef,
  ModelConfig,
  PreviewFile,
} from "@/types";
import { isTauri, savePasteFile, savePasteImage, savePasteText } from "@/services/tauri";
import { listMentionCandidates } from "@/services/api";
import { formatSize } from "@/utils";
import { MentionPopup } from "../MentionPopup";
import { ModelEffortControl } from "./ModelEffortControl";
import { ContextRingButton } from "./ContextRingButton";

import "./index.less";

/** 已插入输入框的引用：token 文本与提交值分离，发送时按 token 是否仍在正文里判定存活。 */
interface MentionToken {
  kind: MentionKind;
  /** 输入框中的字面文本，如 `@src/a.tsx` 或 `@"my docs/a.md"` */
  text: string;
  /** 提交值：文件为工作区相对路径，技能为名称 */
  value: string;
}

/** `@` / `/` 候选浮层状态。 */
interface MentionCandidateState {
  kind: MentionKind;
  query: string;
  /** token 起点（`@` / `/` 的下标） */
  start: number;
  /** 触发时的光标位置 */
  end: number;
  items: MentionCandidate[];
  activeIndex: number;
  loading: boolean;
}

const MENTION_DEBOUNCE_MS = 300;
const MENTION_LIMIT = 8;

const PASTE_AS_FILE_CHAR_THRESHOLD = 2000;
const PASTE_AS_FILE_LINE_THRESHOLD = 500;

// Raster image types the vision model accepts; pasted SVG etc. is not a raster
// image and is saved via the generic file path instead.
const RASTER_IMAGE_MIMES = new Set([
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/gif",
  "image/webp",
]);

interface ComposerProps {
  disabled: boolean;
  /** agent 正在流式执行：输入保持可用，发送走"插话"通道而非新消息 */
  streaming?: boolean;
  /** 流式执行中用户主动补充信息（steering）；纯文本，附件不参与 */
  onSupplement?: (text: string) => void;
  onSend: (question: string, files: ChatFile[], mentions: MentionRef[]) => void;
  onStop?: () => void;
  onPreviewFile?: (file: PreviewFile) => void;
  onValueChange?: (hasValue: boolean) => void;
  approvalMode: ApprovalMode;
  onApprovalModeChange: (mode: ApprovalMode) => void;
  effort: string;
  onEffortChange: (value: string) => void;
  models: ModelConfig[];
  modelId: string | null;
  onModelChange: (modelId: string) => void;
  sessionId?: string | null;
  contextRefreshKey?: number;
  prefill?: { text: string; nonce: number } | null;
  onPrefillConsumed: () => void;
  projectPicker?: ReactNode;
}

export const ChatInput = forwardRef<HTMLTextAreaElement, ComposerProps>(function ChatInput(
  {
    disabled,
    streaming,
    onSupplement,
    onSend,
    onStop,
    onPreviewFile,
    onValueChange,
    approvalMode,
    onApprovalModeChange,
    effort,
    onEffortChange,
    models,
    modelId,
    onModelChange,
    sessionId,
    contextRefreshKey = 0,
    prefill,
    onPrefillConsumed,
    projectPicker,
  },
  ref,
) {
  const { t } = useTranslation();
  const approvalModeLabels: Record<ApprovalMode, string> = {
    ask: t("chat.approvalAsk", "请求批准"),
    assist: t("chat.approvalAssist", "帮我批准"),
    full: t("chat.approvalFull", "完全访问权限"),
  };
  const [value, setValue] = useState("");
  const [attached, setAttached] = useState<ChatFile[]>([]);
  const [mentions, setMentions] = useState<MentionToken[]>([]);
  const [candidate, setCandidate] = useState<MentionCandidateState | null>(null);
  const composingRef = useRef(false);
  const mentionTimerRef = useRef<number | null>(null);
  const mentionAbortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const localRef = useRef<HTMLTextAreaElement>(
    null,
  ) as MutableRefObject<HTMLTextAreaElement | null>;
  const textareaRef = localRef;

  const approvalModeItems = [
    {
      key: "ask" as const,
      label: t("chat.approvalAsk", "请求批准"),
      description: t("chat.approvalAskDescription", "编辑外部文件和使用互联网时始终询问"),
    },
    {
      key: "assist" as const,
      label: t("chat.approvalAssist", "帮我批准"),
      description: t("chat.approvalAssistDescription", "仅检测到危险操作请求批准"),
    },
    {
      key: "full" as const,
      label: t("chat.approvalFull", "完全访问权限"),
      description: t("chat.approvalFullDescription", "可不受限制地访问互联网和您电脑上的任何文件"),
    },
  ];

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
  }, [onPrefillConsumed, onValueChange, prefill, textareaRef]);

  const closeCandidate = () => {
    if (mentionTimerRef.current !== null) {
      window.clearTimeout(mentionTimerRef.current);
      mentionTimerRef.current = null;
    }
    mentionAbortRef.current?.abort();
    mentionAbortRef.current = null;
    setCandidate(null);
  };

  useEffect(() => {
    // 会话切换后工作区可能已变，旧候选与旧 token 一并作废
    setMentions([]);
    setCandidate(null);
    if (mentionTimerRef.current !== null) {
      window.clearTimeout(mentionTimerRef.current);
      mentionTimerRef.current = null;
    }
    mentionAbortRef.current?.abort();
    mentionAbortRef.current = null;
  }, [sessionId]);

  const loadCandidates = (kind: MentionKind, query: string, start: number) => {
    if (mentionTimerRef.current !== null) window.clearTimeout(mentionTimerRef.current);
    mentionTimerRef.current = window.setTimeout(() => {
      mentionTimerRef.current = null;
      mentionAbortRef.current?.abort();
      const controller = new AbortController();
      mentionAbortRef.current = controller;
      void listMentionCandidates({
        q: query,
        sessionId,
        kinds: [kind],
        limit: MENTION_LIMIT,
        signal: controller.signal,
      })
        .then((data) => {
          setCandidate((prev) =>
            prev && prev.start === start
              ? { ...prev, items: data.items, loading: false, activeIndex: 0 }
              : prev,
          );
        })
        .catch(() => {
          setCandidate((prev) =>
            prev && prev.start === start ? { ...prev, items: [], loading: false } : prev,
          );
        });
    }, MENTION_DEBOUNCE_MS);
  };

  const mentionText = (kind: MentionKind, target: string) => {
    if (kind === "skill") return `/${target}`;
    // 含空格的路径用引号包裹，避免插入后又被空白切成两个 token
    return /\s/.test(target) ? `@"${target}"` : `@${target}`;
  };

  const applyMention = (item: MentionCandidate) => {
    if (!candidate) return;
    const token: MentionToken = {
      kind: candidate.kind,
      text: mentionText(candidate.kind, item.path),
      value: item.path,
    };
    const next = `${value.slice(0, candidate.start)}${token.text} ${value.slice(candidate.end)}`;
    const caret = candidate.start + token.text.length + 1;
    setValue(next);
    onValueChange?.(next.trim().length > 0);
    setMentions((prev) => [...prev.filter((entry) => entry.text !== token.text), token]);
    closeCandidate();
    window.requestAnimationFrame(() => {
      const element = textareaRef.current;
      if (!element) return;
      element.focus();
      element.setSelectionRange(caret, caret);
    });
  };

  /** 发送前按「token 文本仍在正文里」判定存活，失效项剔除；顺序为先技能后文件。 */
  const liveMentions = (text: string): MentionRef[] =>
    mentions
      .filter((token) => text.includes(token.text))
      .map((token) =>
        token.kind === "skill"
          ? { type: "skill" as const, name: token.value }
          : { type: "file" as const, path: token.value },
      )
      .sort((a, b) => (a.type === b.type ? 0 : a.type === "skill" ? -1 : 1));

  const send = () => {
    const question = value.trim();
    if (!question && attached.length === 0) return;
    // 流式执行中：Enter/发送按钮 = 向执行中的任务补充信息（纯文本）
    if (streaming) {
      if (!question || !onSupplement) return;
      onSupplement(question);
      setValue("");
      return;
    }
    if (disabled) return;
    onSend(question, attached, liveMentions(value));
    setValue("");
    setAttached([]);
    setMentions([]);
    closeCandidate();
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
    setAttached((prev) => [...prev, { name: file.name, size: file.size, content }]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handlePaste = async (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const native = event.nativeEvent as ClipboardEvent & {
      ctrlKey?: boolean;
      metaKey?: boolean;
      shiftKey?: boolean;
    };
    if (native.ctrlKey && native.shiftKey) return;
    if (native.metaKey && native.shiftKey) return;

    // Clipboard files (pasted screenshots or files copied from Finder):
    // 1) file:// URLs in text/uri-list are referenced by path directly;
    // 2) image items are saved locally and attached by path;
    // 3) other file items use their native path, or are saved locally.
    // The vision pipeline (read_image) sends images as base64 to the vision
    // model when the message goes out.
    if (isTauri()) {
      const fileUrls = fileUrlsFromClipboard(event.clipboardData);
      if (fileUrls.length > 0) {
        event.preventDefault();
        setAttached((prev) => {
          const next = [...prev];
          for (const path of fileUrls) {
            if (next.some((file) => file.path === path)) continue;
            const name = path.split(/[\\/]/).pop() || path;
            next.push({ name, path });
          }
          return next;
        });
        return;
      }

      const fileItem = Array.from(event.clipboardData?.items ?? []).find(
        (item) => item.kind === "file",
      );
      if (fileItem) {
        event.preventDefault();
        const file = fileItem.getAsFile();
        if (file) {
          const nativePath = (file as File & { path?: string }).path;
          if (nativePath) {
            setAttached((prev) => [
              ...prev,
              { name: file.name, path: nativePath, size: file.size },
            ]);
          } else if (RASTER_IMAGE_MIMES.has(file.type)) {
            try {
              const saved = await savePastedImage(file);
              setAttached((prev) => [
                ...prev,
                { name: saved.name, path: saved.path, size: saved.size },
              ]);
            } catch {
              // unsupported format or save failure: keep the paste as-is
            }
          } else {
            try {
              const base64 = await blobToBase64(file);
              const saved = await savePasteFile(base64, file.name);
              setAttached((prev) => [
                ...prev,
                { name: saved.name, path: saved.path, size: saved.size },
              ]);
            } catch {
              // save failure: keep the paste as-is
            }
          }
        }
        return;
      }
    }

    const text = event.clipboardData?.getData("text/plain") || "";
    const lineCount = text.split(/\r?\n/).length;
    const tooLarge =
      text.length >= PASTE_AS_FILE_CHAR_THRESHOLD || lineCount >= PASTE_AS_FILE_LINE_THRESHOLD;
    if (!text || !tooLarge) return;

    event.preventDefault();
    try {
      const saved = await savePasteText(text);
      setAttached((prev) => [...prev, { name: saved.name, path: saved.path, size: saved.size }]);
    } catch {
      setValue((prev) => (prev ? `${prev}\n${text}` : text));
      onValueChange?.(true);
      textareaRef.current?.focus();
    }
  };

  const pickAttachment = async () => {
    if (streaming) return;
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
        {candidate && (
          <MentionPopup
            kind={candidate.kind}
            items={candidate.items}
            activeIndex={candidate.activeIndex}
            loading={candidate.loading}
            onHover={(index) =>
              setCandidate((prev) => (prev ? { ...prev, activeIndex: index } : prev))
            }
            onSelect={applyMention}
          />
        )}
        <TextArea
          ref={setRefs}
          value={value}
          rows={1}
          placeholder={t("chat.inputPlaceholder", "随心输入")}
          onChange={(event) => {
            const next = event.target.value;
            setValue(next);
            onValueChange?.(next.trim().length > 0);
            // 输入法合成期间不弹候选，避免中文选词时浮层乱跳
            if (composingRef.current) return;
            const caret = event.target.selectionStart ?? next.length;
            const trigger = detectMentionTrigger(next, caret);
            if (!trigger) {
              closeCandidate();
              return;
            }
            setCandidate({ ...trigger, items: [], activeIndex: 0, loading: true });
            loadCandidates(trigger.kind, trigger.query, trigger.start);
          }}
          onCompositionStart={() => {
            composingRef.current = true;
          }}
          onCompositionEnd={() => {
            composingRef.current = false;
          }}
          onPaste={(event) => void handlePaste(event)}
          onKeyDown={(event) => {
            // 输入法合成态（中文选词确认的回车）不发送，避免误发消息
            if (isComposingEvent(event.nativeEvent)) return;
            // 候选浮层打开时接管导航键：Enter/Tab 变为“确认引用”
            if (candidate && candidate.items.length > 0) {
              const total = candidate.items.length;
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setCandidate({
                  ...candidate,
                  activeIndex: (candidate.activeIndex + 1) % total,
                });
                return;
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setCandidate({
                  ...candidate,
                  activeIndex: (candidate.activeIndex - 1 + total) % total,
                });
                return;
              }
              if ((event.key === "Enter" || event.key === "Tab") && !event.shiftKey) {
                event.preventDefault();
                applyMention(candidate.items[candidate.activeIndex]);
                return;
              }
            }
            if (event.key === "Escape" && candidate) {
              event.preventDefault();
              closeCandidate();
              return;
            }
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
              <Flex key={attachmentKey(file)} align="center" gap={6} className="attachment-chip">
                <FileTypeIcon name={file.name} size={13} />
                <span
                  className={
                    file.path && onPreviewFile
                      ? "attachment-name attachment-name-preview"
                      : "attachment-name"
                  }
                  role={file.path && onPreviewFile ? "button" : undefined}
                  tabIndex={file.path && onPreviewFile ? 0 : undefined}
                  title={file.path && onPreviewFile ? t("chat.preview", "预览") : undefined}
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
        <Flex align="center" justify="space-between" gap={8} className="composer-toolbar">
          <Flex align="center" gap={4} className="composer-actions">
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.json,.csv,.py,.png,.jpg,.jpeg,.webp,.gif,.bmp,.svg"
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
          <Flex align="center" gap={8}>
            <ModelEffortControl
              disabled={disabled || streaming || models.length === 0}
              models={models}
              modelId={modelId}
              onModelChange={onModelChange}
              effort={effort}
              onEffortChange={onEffortChange}
            />
            {sessionId && (
              <ContextRingButton sessionId={sessionId} refreshKey={contextRefreshKey} />
            )}
            {(() => {
              const hasText = value.trim().length > 0;
              // 单按钮槽位自适应，避免"停止+发送"双按钮并排：
              // 流式执行中且输入框为空 → 停止；其余 → 发送（流式中即"补充到当前任务"）。
              if (streaming && onStop && !hasText) {
                return (
                  <Button
                    variant="primary"
                    className="send-button"
                    onClick={onStop}
                    aria-label={t("chat.stop", "停止生成")}
                    title={t("chat.stop", "停止生成")}
                  >
                    <Square size={14} />
                  </Button>
                );
              }
              if (disabled) return null;
              const enabled = streaming
                ? hasText && Boolean(onSupplement)
                : hasText || attached.length > 0;
              const label = streaming
                ? t("chat.supplement", "补充到当前任务")
                : t("chat.send", "发送");
              return (
                <Button
                  variant="primary"
                  className="send-button"
                  onClick={send}
                  disabled={!enabled}
                  aria-label={label}
                  title={label}
                >
                  <ArrowUp size={16} />
                </Button>
              );
            })()}
          </Flex>
        </Flex>
      </Flex>
      <p className="composer-hint">{t("chat.aiDisclaimer", "内容由 AI 生成，请核实重要信息")}</p>
    </div>
  );
});

/**
 * 光标前是否是 `@` / `/` 触发点：前缀必须是行首或空白（设计 §1.3），
 * 因此 `https://x` 里的 `/` 不会误触发。含空格路径用 `@"..."` 形式。
 */
function detectMentionTrigger(
  text: string,
  caret: number,
): { kind: MentionKind; query: string; start: number; end: number } | null {
  const before = text.slice(0, caret);
  const quoted = /(^|\s)@"([^"\n]*)$/.exec(before);
  if (quoted) {
    return { kind: "file", query: quoted[2], start: caret - quoted[2].length - 2, end: caret };
  }
  const plain = /(^|\s)([@/])([^\s@/\n]*)$/.exec(before);
  if (!plain) return null;
  return {
    kind: plain[2] === "/" ? "skill" : "file",
    query: plain[3],
    start: caret - plain[3].length - 1,
    end: caret,
  };
}

/** Persist a pasted clipboard image locally and return its saved location. */
async function savePastedImage(blob: Blob): Promise<{ name: string; path: string; size: number }> {
  const base64 = await blobToBase64(blob);
  return savePasteImage(base64, blob.type || "image/png");
}

/** Decode file:// URLs from text/uri-list into local file paths. */
function fileUrlsFromClipboard(data: DataTransfer | null): string[] {
  const text = data?.getData("text/uri-list") || "";
  const paths: string[] = [];
  for (const line of text.split(/\r?\n/)) {
    const url = line.trim();
    if (!url.startsWith("file://")) continue;
    let decoded: string;
    try {
      decoded = decodeURIComponent(url.slice("file://".length));
    } catch {
      decoded = url.slice("file://".length);
    }
    // Windows file:///C:/... -> C:/...
    if (/^\/[A-Za-z]:/.test(decoded)) decoded = decoded.slice(1);
    if (decoded && !paths.includes(decoded)) paths.push(decoded);
  }
  return paths;
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}
