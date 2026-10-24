// Browser automation settings section (design 031): channel status + one-click guided launch.
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Globe } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { toast } from "@/components/ui/Toast";
import { request } from "@/services/request";

import "./BrowserSection.less";

interface BrowserStatus {
  running: boolean;
  endpoint: string | null;
  profile_dir: string;
}

/**
 * 浏览器自动化区块：显示调试通道状态，一键引导启动专用 profile 浏览器。
 * 即时生效，不参与设置弹窗底部的保存流（与意图 tab 同模式）。
 */
export function BrowserSection() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<BrowserStatus | null>(null);
  const [launching, setLaunching] = useState(false);

  const load = useCallback(async () => {
    try {
      setStatus(await request<BrowserStatus>("/browser/status"));
    } catch {
      // 后端未升级等场景静默降级：显示未就绪即可
      setStatus({ running: false, endpoint: null, profile_dir: "" });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const setup = useCallback(async () => {
    setLaunching(true);
    try {
      const result = await request<BrowserStatus & { launched?: boolean }>("/browser/setup", {
        method: "POST",
      });
      setStatus({
        running: true,
        endpoint: result.endpoint,
        profile_dir: result.profile_dir ?? "",
      });
      toast.success(
        t(
          "settings.browserSetupDone",
          result.launched ? "专用浏览器已启动并就绪" : "专用浏览器通道已就绪",
        ),
      );
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      toast.error(
        t("settings.browserSetupFailed", "浏览器启动失败") + (detail ? `: ${detail}` : ""),
      );
    } finally {
      setLaunching(false);
    }
  }, [t]);

  return (
    <div className="settings-section settings-browser">
      <h3>
        <Globe size={15} />
        <span>{t("settings.browserSectionTitle", "浏览器自动化")}</span>
      </h3>
      <p className="browser-desc">
        {t(
          "settings.browserDesc",
          "通用 Web 任务引擎通过专用浏览器 Profile 执行网页任务：一次性登录、持久复用，与日常浏览器完全隔离。",
        )}
      </p>
      <div className="settings-field-label-row">
        <span className="browser-channel-label">{t("settings.browserChannel", "调试通道")}</span>
        {status?.running ? (
          <Tag tone="success">{t("settings.browserStatusRunning", "已就绪")}</Tag>
        ) : (
          <Tag tone="warning">{t("settings.browserStatusStopped", "未就绪")}</Tag>
        )}
      </div>
      {status?.endpoint && <p className="browser-desc browser-endpoint">{status.endpoint}</p>}
      <div>
        <Button variant="secondary" onClick={() => void setup()} disabled={launching}>
          {launching
            ? t("settings.browserLaunching", "启动中…")
            : status?.running
              ? t("settings.browserRelaunch", "重新引导启动")
              : t("settings.browserSetup", "一键启动专用浏览器")}
        </Button>
      </div>
    </div>
  );
}
