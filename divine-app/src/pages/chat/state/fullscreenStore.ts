import { useEffect, useState } from "react";
import { isTauri } from "@/services/tauri";

export function useFullscreen() {
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    let active = true;
    const update = async () => {
      let value = false;
      if (isTauri()) {
        try {
          const { getCurrentWindow } = await import("@tauri-apps/api/window");
          value = await getCurrentWindow().isFullscreen();
        } catch {
          value = false;
        }
      } else {
        value = Boolean(document.fullscreenElement);
      }
      if (active) setFullscreen(value);
    };
    void update();
    const onResize = () => void update();
    const onFullscreenChange = () => void update();
    window.addEventListener("resize", onResize);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => {
      active = false;
      window.removeEventListener("resize", onResize);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
    };
  }, []);

  return fullscreen;
}
