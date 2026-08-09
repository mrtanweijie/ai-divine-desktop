import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import "./index.less";

export type ToastType = "success" | "error" | "info";

export interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
}

type Listener = (items: ToastItem[]) => void;

let nextId = 1;
let currentItems: ToastItem[] = [];
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((callback) => callback([...currentItems]));
}

function push(type: ToastType, message: string, duration: number) {
  const id = nextId++;
  currentItems = [...currentItems, { id, type, message }];
  notify();
  window.setTimeout(() => dismiss(id), duration);
}

function dismiss(id: number) {
  currentItems = currentItems.filter((item) => item.id !== id);
  notify();
}

export const toast = {
  success(message: string) {
    push("success", message, 2400);
  },
  error(message: string) {
    push("error", message, 3600);
  },
  info(message: string) {
    push("info", message, 2400);
  },
};

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>(currentItems);

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
        <div
          key={item.id}
          className={`toast toast-${item.type}`}
          role="status"
        >
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
          <Button
            variant="icon"
            size="small"
            className="toast-close"
            onClick={() => dismiss(item.id)}
            aria-label="关闭"
          >
            <X size={13} />
          </Button>
        </div>
      ))}
    </div>
  );
}
