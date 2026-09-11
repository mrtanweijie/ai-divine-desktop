/**
 * AnimationManager —— 动画池 + 视口外暂停 + 流动块上限。
 *
 * 三个硬约束（020 §7 性能硬约束 / §11.5）：
 * 1. **并发动画上限 20**，超限直接置终态（不排队）——排队会让迟到很久的动画
 *    在用户早已移开视线后突然播放；
 * 2. **视口外暂停**：antline 是无限循环动画，长会话里滚出视口不暂停会持续吃 CPU；
 * 3. **会话内同时开启流动的块 ≤ 3**，超出自动关闭最早的（真人不会同时看四张
 *    流动的图，但 CPU 会一直算）。
 */

const MAX_CONCURRENT_ANIMATIONS = 20;
const MAX_FLOW_BLOCKS = 3;

/**
 * 会话级共享的流动名额登记表（按申请顺序）。
 * 超出上限时**关掉最早申请的那个块**——真人不会同时盯四张流动的图，
 * 但 CPU 会一直算。被挤出的块会收到自己的 close 回调（= 关掉流动）。
 */
const activeFlowBlocks: { id: symbol; close: () => void }[] = [];

export class AnimationManager {
  private readonly id = Symbol("graph-block");
  private holdingFlowSlot = false;
  private readonly timers = new Set<number>();
  private observer: IntersectionObserver | null = null;
  private paused = false;

  /** 登记一段有时长的动画；超池直接跳过（终态优先，不排队）。 */
  track(_name: string, durationMs: number, onDone?: () => void): void {
    if (this.timers.size >= MAX_CONCURRENT_ANIMATIONS) return;
    const timer = window.setTimeout(() => {
      this.timers.delete(timer);
      onDone?.();
    }, durationMs);
    this.timers.add(timer);
  }

  /**
   * 申请流动名额。名额已满时先关闭最早的块（调用它自己的 close），
   * 再登记当前块——保证"最多 3 个块同时流动"是硬约束而非建议。
   */
  claimFlowSlot(closeCurrent: () => void): void {
    if (this.holdingFlowSlot) {
      // 已在名额内，更新 close 回调（重播等场景下回调可能变化）
      const existing = activeFlowBlocks.find((item) => item.id === this.id);
      if (existing) existing.close = closeCurrent;
      return;
    }
    if (activeFlowBlocks.length >= MAX_FLOW_BLOCKS) {
      const evicted = activeFlowBlocks.shift();
      evicted?.close();
    }
    activeFlowBlocks.push({ id: this.id, close: closeCurrent });
    this.holdingFlowSlot = true;
  }

  releaseFlowSlot(): void {
    const index = activeFlowBlocks.findIndex((item) => item.id === this.id);
    if (index >= 0) activeFlowBlocks.splice(index, 1);
    this.holdingFlowSlot = false;
  }

  /** 视口外暂停：容器进入/离开视口时切换（虚拟滚动列表里也可靠）。 */
  observe(container: HTMLElement): void {
    if (typeof IntersectionObserver === "undefined") return;
    this.observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) this.resume("viewport");
          else this.pause("viewport");
        }
      },
      { threshold: 0 },
    );
    this.observer.observe(container);
  }

  pause(_reason: string): void {
    if (this.paused) return;
    this.paused = true;
    document.documentElement.classList.add("gb-paused");
  }

  resume(_reason: string): void {
    if (!this.paused) return;
    this.paused = false;
    document.documentElement.classList.remove("gb-paused");
  }

  disposeAll(): void {
    for (const timer of this.timers) window.clearTimeout(timer);
    this.timers.clear();
    this.observer?.disconnect();
    this.observer = null;
    this.releaseFlowSlot();
  }
}
