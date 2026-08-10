import { useEffect, useState, type ReactNode } from "react";
import { request } from "@/services/request";
import { isTauri } from "@/services/tauri";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import "./index.less";

const MIN_LOADING_MS = 1000;

interface StartupGateProps {
  children: ReactNode;
}

function useBackendReady(): boolean {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const check = async () => {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 2000);
      try {
        const data = await request<{ status?: string } | null>("/health", {
          cache: "no-store",
          signal: controller.signal,
          throwOnError: false,
        });
        if (data?.status === "ok" && !cancelled) {
          setReady(true);
          return;
        }
      } catch {
        // sidecar is still starting
      } finally {
        window.clearTimeout(timeout);
      }
      if (!cancelled) {
        timer = window.setTimeout(check, 800);
      }
    };

    void check();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  return ready;
}

export function StartupGate({ children }: StartupGateProps) {
  const ready = useBackendReady();
  const [minTimeElapsed, setMinTimeElapsed] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setMinTimeElapsed(true), MIN_LOADING_MS);
    return () => window.clearTimeout(timer);
  }, []);

  if (!ready || !minTimeElapsed) {
    return (
      <div
        className="startup-gate"
        {...(isTauri() ? { "data-tauri-drag-region": true } : {})}
      >
        <LoadingOrb state="connecting" size={64} />
      </div>
    );
  }

  return <>{children}</>;
}
