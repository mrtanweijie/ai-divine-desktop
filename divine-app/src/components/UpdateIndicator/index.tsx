// 更新状态图标（2026-11-04 用户指定）：挂在侧栏「设置」行右侧，替代原来的浮层横幅。
//
// 状态 → 图标：
//   available   下载图标（点击开始下载）
//   downloading 只转圈（进度写进 title，不铺文字）
//   downloaded  重启图标（点击重启应用；不再自动重启）
// 失败态不在这里提示（与旧横幅一致）：错误详情只在设置 → 关于里展示。
import { Download, Loader2, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  downloadAndInstallUpdate,
  restartToApplyUpdate,
  useUpdaterState,
} from "@/services/updater";
import "./index.less";

interface IndicatorAction {
  label: string;
  icon: ReactNode;
  run: () => void;
}

export function UpdateIndicator() {
  const { t } = useTranslation();
  const updater = useUpdaterState();

  if (updater.status === "downloading") {
    const label = t("updater.downloading", "正在下载 v{{version}} {{progress}}%", {
      version: updater.version,
      progress: updater.progress,
    });
    return (
      <span
        className="update-indicator is-downloading"
        role="status"
        title={label}
        aria-label={label}
      >
        <Loader2 size={13} className="update-indicator-spin" />
      </span>
    );
  }

  let action: IndicatorAction | null = null;
  if (updater.status === "available") {
    action = {
      label: t("updater.availableAction", "发现新版本 v{{version}}，点击下载", {
        version: updater.version,
      }),
      icon: <Download size={13} />,
      run: () => void downloadAndInstallUpdate(),
    };
  } else if (updater.status === "downloaded") {
    action = {
      // message 非空 = 上次重启失败：仍可点，文案改说「请手动退出重开」
      label: updater.message
        ? t("updater.manualRestart", "更新已安装，请手动退出并重新打开应用")
        : t("updater.restartAction", "更新已就绪，点击重启"),
      icon: <RotateCcw size={13} />,
      run: () => void restartToApplyUpdate(),
    };
  }

  if (!action) return null;

  return (
    <div
      role="button"
      tabIndex={0}
      className={`update-indicator is-${updater.status}`}
      title={action.label}
      aria-label={action.label}
      onClick={action.run}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          action.run();
        }
      }}
    >
      {action.icon}
    </div>
  );
}
