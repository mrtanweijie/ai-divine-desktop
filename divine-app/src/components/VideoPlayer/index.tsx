// 视频播放器（035 §8.2）：消息卡片 / 任务面板 / 文件预览复用同一组件。
//
// src 必须走 `/api/files/media`（Range 流式，能拖进度条）；
// 组件卸载/切源时主动 pause 并清空 src，否则会出现"关了预览还在响"。

import { useEffect, useRef } from "react";
import "./index.less";

interface VideoPlayerProps {
  src: string;
  poster?: string;
  /** 竖屏视频限高（9:16 等），避免撑爆容器 */
  vertical?: boolean;
  onError?: (message: string) => void;
}

export function VideoPlayer({ src, poster, vertical, onError }: VideoPlayerProps) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = ref.current;
    return () => {
      // 切文件 / 卸载：只 pause，**不要 removeAttribute("src")**。
      //
      // 曾经的写法是「pause + remove src + load」，本意是防止关掉预览后还在响，
      // 但 React 的 effect cleanup 在 **DOM 属性已更新之后**才跑，且 dev 的
      // StrictMode 会「挂载 → cleanup → 再挂载」双调用：cleanup 把 React 刚设好的
      // src 抹掉，第二次挂载又不会重设属性（src 来自 JSX，只在渲染时写入），
      // 于是 <video> 永远停在 readyState 0 —— 控件在、时长 00:00、画面全黑
      // （2026-11-04 用户三次反馈「弹窗没法播放」的真因）。
      //
      // 换源由 React 更新 src 属性触发，浏览器会自动中止旧播放；卸载时元素销毁
      // 本身就不会再出声，pause 已经够。
      video?.pause();
    };
  }, [src]);

  return (
    <div className={`video-player${vertical ? " is-vertical" : ""}`}>
      <video
        ref={ref}
        src={src}
        poster={poster}
        controls
        preload="metadata"
        playsInline
        onError={() => onError?.("视频加载失败：文件可能已被移动或删除")}
      />
    </div>
  );
}
