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
      // 切文件 / 关闭面板：先停再清源，防止后台继续出声
      if (video) {
        video.pause();
        video.removeAttribute("src");
        video.load();
      }
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
