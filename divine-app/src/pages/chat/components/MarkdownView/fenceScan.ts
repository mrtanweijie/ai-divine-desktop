/**
 * 未闭合代码围栏的**增量**扫描。
 *
 * 从 MarkdownView 抽出来是为了可单独验证：流式每帧 content 都在增长，
 * 原先的实现每帧都要 `content.split("\n")` 为全文建一次行数组，
 * 长代码块流式期间是每帧 O(全文)。这里只扫新增的行。
 *
 * 抽成独立模块的另一个好处是它不依赖 React，能直接跑等价性对拍。
 *
 * **两段式的关键**：末尾那半行（还没换行的）必须每次重看，因为它可能继续
 * 变长（` `` ` → ` ``` `）。如果把它和完整行混在一起累计，重扫时会把它的
 * 围栏开关效果叠加两次——`"a\n```t"` 会被误判成「已闭合」。
 * 所以：
 *   1. `scanFences` 只累计**完整行**（到最后一个 \n 为止）；
 *   2. `unclosedFenceStart` 在完整行结论上叠加末尾半行，得出要报告的偏移。
 */

/** 扫描状态。open/fenceStart 只反映「已完整」的行。 */
export interface FenceScanState {
  /** 上次扫过的内容；只有本次 content 以它为前缀时才能续扫 */
  content: string;
  open: boolean;
  fenceStart: number;
  /** 已推进到 content 的哪个偏移（停在最后一个 \n 之后） */
  scannedUpTo: number;
}

export const EMPTY_FENCE_SCAN: FenceScanState = {
  content: "",
  open: false,
  fenceStart: -1,
  scannedUpTo: 0,
};

/** 仅识别 ≤3 空格缩进的顶层围栏 */
const FENCE_RE = /^ {0,3}(```|~~~)/;

/**
 * 累计**完整行**（以 \n 结尾的行）的围栏状态；末尾半行不在这里处理。
 *
 * 与「每帧全量 split 扫描」在完整行上的结论一致，但流式时只扫新增行：
 * - 内容没变 → 直接复用上次状态；
 * - 是上次的前缀扩展 → 从上次的 scannedUpTo 续扫；
 * - 否则（切会话 / 重答 / 编辑）→ 从头扫。
 */
export function scanFences(prev: FenceScanState, content: string): FenceScanState {
  if (content === prev.content) return prev;

  let open = false;
  let fenceStart = -1;
  let from = 0;
  if (content.startsWith(prev.content)) {
    open = prev.open;
    fenceStart = prev.fenceStart;
    from = prev.scannedUpTo;
  }

  let lineStart = from;
  while (lineStart < content.length) {
    const nl = content.indexOf("\n", lineStart);
    if (nl === -1) break; // 末尾半行留给 unclosedFenceStart
    if (FENCE_RE.test(content.slice(lineStart, nl))) {
      if (open) {
        open = false;
        fenceStart = -1;
      } else {
        open = true;
        fenceStart = lineStart;
      }
    }
    lineStart = nl + 1;
  }

  return { content, open, fenceStart, scannedUpTo: lineStart };
}

/**
 * 当前应报告的「最后一个未闭合围栏的起始偏移」；无未闭合围栏返回 -1。
 *
 * = 完整行结论（state）叠加末尾半行。半行每次重算，但只切这一小段，
 * 不涉及全文。
 */
export function unclosedFenceStart(state: FenceScanState, content: string): number {
  const lineStart = content.lastIndexOf("\n") + 1;
  if (lineStart >= content.length) return state.fenceStart;
  if (!FENCE_RE.test(content.slice(lineStart))) return state.fenceStart;
  // 末尾半行本身是个围栏行 → 与完整行的 open 状态叠加（开则闭、闭则开）
  return state.open ? -1 : lineStart;
}
