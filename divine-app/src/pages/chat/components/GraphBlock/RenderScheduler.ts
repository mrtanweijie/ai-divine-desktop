/**
 * RenderScheduler —— 80ms 窗口批处理。
 *
 * 为什么需要：入场是"一次性到达 + 前端回放"，同一拍里可能有几十个 DOM 改动
 * （节点类名、边动画、详情面板），逐条同步执行会把主线程切成碎片。
 * 攒到一个动画帧窗口里成批执行，观感更稳（004 架构图 / 020 §7）。
 */

type Task = () => void;

export class RenderScheduler {
  private queue: Task[] = [];
  private timer: number | null = null;

  constructor(private readonly windowMs = 80) {}

  schedule(task: Task): void {
    this.queue.push(task);
    if (this.timer !== null) return;
    this.timer = window.setTimeout(() => {
      this.timer = null;
      const batch = this.queue;
      this.queue = [];
      this.run(batch);
    }, this.windowMs);
  }

  /** 立即冲刷（用户点了"重播"这类显式操作时不等窗口）。 */
  flush(): void {
    if (this.timer !== null) {
      window.clearTimeout(this.timer);
      this.timer = null;
    }
    const batch = this.queue;
    this.queue = [];
    this.run(batch);
  }

  dispose(): void {
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.timer = null;
    this.queue = [];
  }

  private run(batch: Task[]): void {
    for (const task of batch) {
      try {
        task();
      } catch (error) {
        // 一条任务失败不能拖垮整批渲染
        console.error("[GraphBlock] 调度任务失败:", error);
      }
    }
  }
}

/** 尊重系统的"减少动态效果"设置（020 §11.5）。 */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
