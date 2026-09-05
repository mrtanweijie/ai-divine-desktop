// B2（流式渲染优化）：SSE 文本增量缓冲。
// think/message 每个 chunk 都会触发一次全量消息数组重建 + Markdown 全量
// 重解析，长回答累计 O(n²)。这里把增量先累进缓冲区，requestAnimationFrame
// 到点合并成一次 commit——渲染频率从每 chunk 一次降到帧对齐（≤60Hz）。

export interface PendingText {
  think: string;
  content: string;
}

export interface StreamBuffer {
  pushThink: (text: string) => void;
  pushContent: (text: string) => void;
  /** 同步提交缓冲区里的全部增量（done/error/中断前必须调用，防丢尾字） */
  flush: () => void;
  /** 丢弃缓冲区并取消已排定的帧回调（流生命周期结束时调用） */
  dispose: () => void;
}

export function createStreamBuffer(commit: (pending: PendingText) => void): StreamBuffer {
  let pending: PendingText = { think: "", content: "" };
  let raf: number | null = null;

  const flushNow = () => {
    raf = null;
    if (!pending.think && !pending.content) return;
    const batch = pending;
    pending = { think: "", content: "" };
    commit(batch);
  };

  const schedule = () => {
    if (raf === null) raf = requestAnimationFrame(flushNow);
  };

  return {
    pushThink(text) {
      if (!text) return;
      pending.think += text;
      schedule();
    },
    pushContent(text) {
      if (!text) return;
      pending.content += text;
      schedule();
    },
    flush() {
      if (raf !== null) {
        cancelAnimationFrame(raf);
        raf = null;
      }
      flushNow();
    },
    dispose() {
      if (raf !== null) {
        cancelAnimationFrame(raf);
        raf = null;
      }
      pending = { think: "", content: "" };
    },
  };
}
