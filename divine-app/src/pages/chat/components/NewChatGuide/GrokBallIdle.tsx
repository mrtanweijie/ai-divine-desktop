import { useEffect, useRef } from "react";

import { GrokBall, SHY_EMOTION } from "./DivineBall";

interface GrokBallInstance {
  setEmotion(id: string): void;
  setGaze(nx: number, ny: number): void;
  destroy(): void;
}

/**
 * Grok Ball 害羞（shy）动画球：目光躲闪 + 鼠标跟随；默认脸颊 1.5 秒内泛粉，
 * 传 blush={false} 可关闭泛粉（保持米白球体）。
 */
export function GrokBallIdle({
  size = 88,
  color,
  blush = true,
}: {
  size?: number;
  color?: string;
  blush?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let ball: GrokBallInstance | null = null;
    try {
      // 关闭泛粉：注册一个无粉色变体（body 与序列终态都保持米白）
      if (!blush) {
        const base = SHY_EMOTION as unknown as Record<string, unknown>;
        GrokBall.config.register({
          ...base,
          body: { ...(base.body as Record<string, unknown>), color: "#F3F0EA" },
          sequence: {
            settle: "hold",
            frames: [{ at: 0, body: { color: "#F3F0EA" } }],
          },
        });
      }
      ball = GrokBall.create(container, color ? { color } : undefined);
      ball?.setEmotion("14");
    } catch {
      // 引擎初始化失败时保持空白容器
      return;
    }

    const onMouseMove = (event: MouseEvent) => {
      // 以整个 new-chat-guide 区域为跟随范围：鼠标在引导页内移动即获得
      // 完整眼动范围；找不到容器时回退到窗口范围。
      const guide = container.closest(".new-chat-guide");
      const rect = guide?.getBoundingClientRect();
      let nx: number;
      let ny: number;
      if (rect && rect.width > 0 && rect.height > 0) {
        nx = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        ny = ((event.clientY - rect.top) / rect.height) * 2 - 1;
      } else {
        nx = (event.clientX / window.innerWidth) * 2 - 1;
        ny = (event.clientY / window.innerHeight) * 2 - 1;
      }
      ball?.setGaze(Math.max(-1, Math.min(1, nx)), Math.max(-1, Math.min(1, ny)));
    };
    window.addEventListener("mousemove", onMouseMove);

    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      try {
        ball?.destroy();
      } catch {
        // 忽略销毁异常
      }
      container.replaceChildren();
    };
  }, [color, blush]);

  return (
    <div ref={containerRef} className="grok-ball-idle" style={{ width: size, height: size }} />
  );
}
