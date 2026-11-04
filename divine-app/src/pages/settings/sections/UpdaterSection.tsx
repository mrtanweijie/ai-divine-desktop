import { AlertTriangle, Download, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import {
  checkForUpdates,
  downloadAndInstallUpdate,
  restartToApplyUpdate,
  useUpdaterState,
} from "@/services/updater";
import "./UpdaterSection.less";

export function UpdaterSection() {
  const { t } = useTranslation();
  const updater = useUpdaterState();
  // 失败发生在哪一段要说清楚：下载失败（网络）与安装失败（解压/替换 app）
  // 的处置方式完全不同，原来一律报「检查更新失败」等于没说。
  const stageLabel =
    updater.errorStage === "install"
      ? t("updater.installFailed", "更新安装失败")
      : updater.errorStage === "download"
        ? t("updater.downloadFailed", "更新下载失败")
        : t("updater.checkFailed", "检查更新失败，请稍后重试");

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
            {t("updater.download", "下载更新")}
          </Button>
        )}
        {updater.status === "downloaded" && (
          <Button variant="primary" size="small" onClick={() => void restartToApplyUpdate()}>
            {t("updater.restartNow", "立即重启")}
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
                <span>
                  {updater.message
                    ? t("updater.manualRestart", "更新已安装，请手动退出并重新打开应用")
                    : t("updater.installed", "更新已安装，重启后生效")}
                </span>
              </>
            )}
            {updater.status === "uptodate" && <span>{t("updater.uptodate", "已是最新版本")}</span>}
            {updater.status === "error" && (
              <span className="settings-updater-error">
                <AlertTriangle size={13} />
                {/* 只给一句人话。底层错误（reqwest 的 url/状态码）写进控制台供排查，不糊到脸上 */}
                <span>{stageLabel}</span>
              </span>
            )}
            {updater.status === "disabled" && (
              <span>{t("updater.disabled", "当前环境不支持自动更新")}</span>
            )}
          </span>
        )}
      </div>
    </div>
  );
}
