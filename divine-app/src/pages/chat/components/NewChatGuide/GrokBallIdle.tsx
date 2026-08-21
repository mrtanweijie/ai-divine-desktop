import { useEffect, useRef } from "react";

import { GrokBall } from "./DivineBall";

interface GrokBallInstance {
  setEmotion(id: string): void;
  setGaze(nx: number, ny: number): void;
  destroy(): void;
}

/**
 * Grok Ball 待机放空（idle）动画球：眼睛跟随鼠标、左右张望、呼吸起伏、
 * 随机自旋彩带与小弹跳。容器尺寸即球尺寸。
 */
export function GrokBallIdle({
  size = 88,
  color,
}: {
  size?: number;
  color?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let ball: GrokBallInstance | null = null;
    try {
      // 默认米白球体，两种主题保持一致
      ball = GrokBall.create(container, color ? { color } : undefined);
      ball?.setEmotion("02");
    } catch {
      // 引擎初始化失败时保持空白容器
      return;
    }

    const onMouseMove = (event: MouseEvent) => {
      const nx = Math.max(
        -1,
        Math.min(1, (event.clientX / window.innerWidth) * 2 - 1)
      );
      const ny = Math.max(
        -1,
        Math.min(1, (event.clientY / window.innerHeight) * 2 - 1)
      );
      ball?.setGaze(nx, ny);
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
  }, [color]);

  return (
    <div
      ref={containerRef}
      className="grok-ball-idle"
      style={{ width: size, height: size }}
    />
  );
}
