import {
  Download,
  Loader2,
  RefreshCw,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import {
  dismissUpdateBanner,
  downloadAndInstallUpdate,
  useSettingsOpen,
  useUpdaterState,
} from "@/services/updater";
import "./index.less";

export function UpdateBanner() {
  const { t } = useTranslation();
  const updater = useUpdaterState();
  const settingsOpen = useSettingsOpen();
  if (settingsOpen) return null;

  const visible =
    (updater.status === "available" && !updater.bannerDismissed) ||
    updater.status === "downloading" ||
    updater.status === "downloaded";
  if (!visible) return null;

  if (updater.status === "downloading") {
    return (
      <div className="update-banner update-banner--downloading" role="status">
        <Loader2 className="update-banner-icon" size={15} />
        <span className="update-banner-text">
          {t("updater.downloading", "正在下载更新 {{version}} {{progress}}%", {
            version: updater.version,
            progress: updater.progress,
          })}
        </span>
      </div>
    );
  }

  if (updater.status === "downloaded") {
    return (
      <div className="update-banner" role="status">
        <RefreshCw className="update-banner-icon" size={15} />
        <span className="update-banner-text">
          {t("updater.restarting", "更新完成，正在重启...")}
        </span>
      </div>
    );
  }

  return (
    <div className="update-banner update-banner--available" role="status">
      <Download className="update-banner-icon" size={15} />
      <span className="update-banner-text" title={updater.body || undefined}>
        {t("updater.available", "发现新版本 v{{version}}", {
          version: updater.version,
        })}
      </span>
      <Button
        variant="primary"
        size="small"
        onClick={() => void downloadAndInstallUpdate()}
      >
        {t("updater.downloadAndRestart", "下载并重启")}
      </Button>
      <Button
        variant="icon"
        size="small"
        className="update-banner-close"
        onClick={dismissUpdateBanner}
        aria-label={t("common.close", "关闭")}
      >
        <X size={13} />
      </Button>
    </div>
  );
}
