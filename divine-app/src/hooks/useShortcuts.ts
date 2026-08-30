import { useEffect, useRef } from "react";
import {
  DEFAULT_KEYMAP,
  matchesShortcut,
  type ShortcutDef,
} from "@/config/keymap";

type Action = () => void;

interface RegistryEntry {
  def: ShortcutDef;
  action: { current: Action | null };
}

// 模块级注册表 + 单一 window 监听器：整个应用只挂一次 keydown，
// 动作回调经 ref 刷新（组件无需 memo 回调，也不随渲染重挂监听器）。
const registry = new Map<string, RegistryEntry>();
let listening = false;

function handleKeyDown(event: KeyboardEvent) {
  for (const entry of registry.values()) {
    if (entry.def.layer !== "app") continue;
    if (!matchesShortcut(event, entry.def)) continue;
    const action = entry.action.current;
    if (action) {
      event.preventDefault();
      action();
      return;
    }
  }
}

function ensureListener() {
  if (listening) return;
  window.addEventListener("keydown", handleKeyDown);
  listening = true;
}

/**
 * 注册应用内快捷键动作（id 见 config/keymap.ts 的 DEFAULT_KEYMAP）。
 * 组件卸载自动注销；动作回调每渲染刷新，无需 useCallback。
 */
export function useShortcutAction(id: string, action: Action): void {
  const actionRef = useRef(action);
  useEffect(() => {
    actionRef.current = action;
  });

  useEffect(() => {
    const def = DEFAULT_KEYMAP.find((item) => item.id === id);
    if (!def || def.layer !== "app") return;
    ensureListener();
    const entry: RegistryEntry = {
      def,
      action: { current: () => actionRef.current() },
    };
    registry.set(id, entry);
    return () => {
      registry.delete(id);
    };
  }, [id]);
}
