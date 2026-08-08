import { useEffect, useState, type ReactNode } from "react";
import { apiBase } from "@/services/api";
import { LoadingOrb } from "@/components/ui/LoadingOrb";
import "./index.less";

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
        const response = await fetch(`${apiBase()}/health`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (response.ok) {
          const data = (await response.json().catch(() => null)) as {
            status?: string;
          } | null;
          if (data?.status === "ok" && !cancelled) {
            setReady(true);
            return;
          }
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

  if (!ready) {
    return (
      <div className="startup-gate">
        <LoadingOrb state="connecting" size={64} />
      </div>
    );
  }

  return <>{children}</>;
}
