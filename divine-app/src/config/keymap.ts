// 统一快捷键事实源（唯一 keymap 定义处）。
// 两层结构：
// - layer "app"：WebView 内生效，由 useShortcuts 的单一 window 监听分发；
// - layer "global"：系统级全局快捷键，Rust 侧注册（lib.rs），这里仅作
//   键位声明与设置页展示；全局开关经 invoke set_global_shortcut_enabled。

export interface ShortcutDef {
  id: string;
  /** 主键（KeyboardEvent.key 的小写形式） */
  key: string;
  /** 修饰键：macOS → ⌘（metaKey），其他平台 → Ctrl（ctrlKey） */
  mod: boolean;
  shift?: boolean;
  alt?: boolean;
  layer: "app" | "global";
  labelKey: string;
}

/** Rust 侧注册的全局快捷键（与 lib.rs 保持一致） */
export const GLOBAL_TOGGLE_SHORTCUT = "CmdOrCtrl+Shift+D";

export const DEFAULT_KEYMAP: ShortcutDef[] = [
  {
    id: "session.new",
    key: "n",
    mod: true,
    layer: "app",
    labelKey: "shortcuts.newSession",
  },
  {
    id: "session.search",
    key: "f",
    mod: true,
    layer: "app",
    labelKey: "shortcuts.searchSessions",
  },
  {
    id: "composer.focus",
    key: "k",
    mod: true,
    layer: "app",
    labelKey: "shortcuts.focusComposer",
  },
  {
    id: "composer.toggleThinking",
    key: "t",
    mod: true,
    shift: true,
    layer: "app",
    labelKey: "shortcuts.toggleThinking",
  },
  {
    id: "window.toggle",
    key: "d",
    mod: true,
    shift: true,
    layer: "global",
    labelKey: "shortcuts.toggleWindow",
  },
];

export function isMacPlatform(): boolean {
  if (typeof navigator === "undefined") return false;
  const uaData = (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData
    ?.platform;
  const platform = uaData ?? navigator.platform ?? "";
  return /Mac|iPhone|iPad/i.test(platform);
}

/** 修饰键按平台归一化（修复旧实现 macOS 上只有字面 Ctrl 才触发的问题）。 */
export function modPressed(event: KeyboardEvent, isMac = isMacPlatform()): boolean {
  return isMac ? event.metaKey : event.ctrlKey;
}

/** 输入法合成态（选词确认的回车等）不应触发任何快捷键/发送。 */
export function isComposingEvent(event: { isComposing?: boolean; keyCode?: number }): boolean {
  return Boolean(event.isComposing) || event.keyCode === 229;
}

export function matchesShortcut(
  event: KeyboardEvent,
  def: ShortcutDef,
  isMac = isMacPlatform(),
): boolean {
  if (isComposingEvent(event)) return false;
  if (def.mod !== modPressed(event, isMac)) return false;
  if (Boolean(def.shift) !== event.shiftKey) return false;
  if (Boolean(def.alt) !== event.altKey) return false;
  return event.key.toLowerCase() === def.key;
}

/** 设置页展示用键位文本：macOS 显示 ⌘ ⇧ D，其他平台显示 Ctrl+Shift+D。 */
export function formatShortcut(def: ShortcutDef, isMac = isMacPlatform()): string {
  const parts: string[] = [];
  if (def.mod) parts.push(isMac ? "⌘" : "Ctrl");
  if (def.alt) parts.push(isMac ? "⌥" : "Alt");
  if (def.shift) parts.push(isMac ? "⇧" : "Shift");
  parts.push(def.key.toUpperCase());
  return parts.join(isMac ? " " : "+");
}
