import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import "./index.less";

export type ToastType = "success" | "error" | "info";

/** 可选的点击动作（如"打开文件夹"）；触发后 toast 随之关闭 */
export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
  action?: ToastAction;
}

type Listener = (items: ToastItem[]) => void;

let nextId = 1;
let currentItems: ToastItem[] = [];
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((callback) => callback([...currentItems]));
}

function push(type: ToastType, message: string, duration: number, action?: ToastAction) {
  const id = nextId++;
  currentItems = [...currentItems, { id, type, message, action }];
  notify();
  // 带动作的 toast 需要留给用户点击的时间，自动延长到至少 5s
  window.setTimeout(() => dismiss(id), action ? Math.max(duration, 5000) : duration);
}

function dismiss(id: number) {
  currentItems = currentItems.filter((item) => item.id !== id);
  notify();
}

export const toast = {
  success(message: string, action?: ToastAction) {
    push("success", message, 2400, action);
  },
  error(message: string, action?: ToastAction) {
    push("error", message, 3600, action);
  },
  info(message: string, action?: ToastAction) {
    push("info", message, 2400, action);
  },
};

/** 动作元素：普通可点击元素走 div + role 语义 + 键盘事件（项目 UI 规范，不用原生 button） */
function handleActionKeyDown(
  event: ReactKeyboardEvent<HTMLDivElement>,
  action: ToastAction,
): boolean {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    action.onClick();
    return true;
  }
  return false;
}

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>(currentItems);
  const { t } = useTranslation();

  useEffect(() => {
    const callback: Listener = (next) => setItems(next);
    listeners.add(callback);
    return () => {
      listeners.delete(callback);
    };
  }, []);

  return (
    <div className="toast-container" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className={`toast toast-${item.type}`} role="status">
          <span className="toast-icon">
            {item.type === "success" ? (
              <CheckCircle2 size={16} />
            ) : item.type === "error" ? (
              <AlertCircle size={16} />
            ) : (
              <Info size={16} />
            )}
          </span>
          <span className="toast-message">{item.message}</span>
          {item.action && (
            <div
              role="button"
              tabIndex={0}
              className="toast-action"
              onClick={() => {
                item.action?.onClick();
                dismiss(item.id);
              }}
              onKeyDown={(event) => {
                if (item.action && handleActionKeyDown(event, item.action)) {
                  dismiss(item.id);
                }
              }}
            >
              {item.action.label}
            </div>
          )}
          <Button
            variant="icon"
            size="small"
            className="toast-close"
            onClick={() => dismiss(item.id)}
            aria-label={t("common.close", "关闭")}
          >
            <X size={13} />
          </Button>
        </div>
      ))}
    </div>
  );
}
