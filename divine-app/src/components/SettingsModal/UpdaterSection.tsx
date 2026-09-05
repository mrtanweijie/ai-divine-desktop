import { AlertTriangle, Download, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { checkForUpdates, downloadAndInstallUpdate, useUpdaterState } from "@/services/updater";
import "./UpdaterSection.less";

export function UpdaterSection() {
  const { t } = useTranslation();
  const updater = useUpdaterState();

  return (
    <div className="settings-updater">
      <span className="ui-field-label">{t("updater.title", "软件更新")}</span>
      <div className="settings-updater-actions">
        {(updater.status === "idle" ||
          updater.status === "uptodate" ||
          updater.status === "error" ||
          updater.status === "checking") && (
          <Button
            variant="secondary"
            size="small"
            loading={updater.status === "checking"}
            onClick={() => void checkForUpdates()}
          >
            {updater.status === "error"
              ? t("updater.retry", "重试")
              : updater.status === "checking"
                ? t("updater.checking", "检查中...")
                : t("updater.check", "检查更新")}
          </Button>
        )}
        {updater.status === "available" && (
          <Button variant="primary" size="small" onClick={() => void downloadAndInstallUpdate()}>
            {t("updater.downloadAndRestart", "下载并重启")}
          </Button>
        )}
        {updater.status !== "idle" && updater.status !== "checking" && (
          <span className={`settings-updater-status settings-updater-status--${updater.status}`}>
            {updater.status === "available" && (
              <>
                <Download size={14} />
                <span>
                  {t("updater.available", "发现新版本 v{{version}}", {
                    version: updater.version,
                  })}
                </span>
              </>
            )}
            {updater.status === "downloading" && (
              <>
                <RefreshCw size={14} />
                <span>
                  {t("updater.downloading", "正在下载 v{{version}} {{progress}}%", {
                    version: updater.version,
                    progress: updater.progress,
                  })}
                </span>
              </>
            )}
            {updater.status === "downloaded" && (
              <>
                <RefreshCw size={14} />
                <span>{t("updater.restarting", "更新完成，正在重启...")}</span>
              </>
            )}
            {updater.status === "uptodate" && <span>{t("updater.uptodate", "已是最新版本")}</span>}
            {updater.status === "error" && (
              <span className="settings-updater-error">
                <AlertTriangle size={13} />
                {t("updater.checkFailed", "检查更新失败，请稍后重试")}
              </span>
            )}
            {updater.status === "disabled" && (
              <span>{t("updater.disabled", "当前环境不支持自动更新")}</span>
            )}
          </span>
        )}
      </div>
      {updater.status === "available" && updater.body && (
        <p className="settings-updater-notes">{updater.body}</p>
      )}
    </div>
  );
}
