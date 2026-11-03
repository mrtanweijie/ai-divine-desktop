// Browser automation settings section (design 031): channel status, guided launch,
// domain policies and shopping guards.
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Tag } from "@/components/ui/Tag";
import { toast } from "@/components/ui/Toast";
import { request } from "@/services/request";

import "./BrowserSection.less";

interface BrowserStatus {
  running: boolean;
  endpoint: string | null;
  profile_dir: string;
}

interface PolicyState {
  browser_mode: "headless" | "headed";
  browser_blocked_domains: string;
  browser_confirm_domains: string;
  shopping_per_order_cap: string;
  shopping_monthly_cap: string;
  shopping_default_address: string;
}

const EMPTY_POLICY: PolicyState = {
  browser_mode: "headed",
  browser_blocked_domains: "",
  browser_confirm_domains: "",
  shopping_per_order_cap: "200",
  shopping_monthly_cap: "",
  shopping_default_address: "",
};

/**
 * 浏览器自动化区块：调试通道状态 + 一键引导启动 + 域名策略/购物护栏编辑。
 * 策略即时保存（独立保存按钮），不参与设置弹窗底部的保存流。
 */
export function BrowserSection() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<BrowserStatus | null>(null);
  const [launching, setLaunching] = useState(false);
  const [policyOpen, setPolicyOpen] = useState(false);
  const policyRef = useRef<HTMLDetailsElement>(null);
  const [policy, setPolicy] = useState<PolicyState>(EMPTY_POLICY);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setStatus(await request<BrowserStatus>("/browser/status"));
    } catch {
      // 后端未升级等场景静默降级：显示未就绪即可
      setStatus({ running: false, endpoint: null, profile_dir: "" });
    }
    try {
      const settings = await request<Record<string, unknown>>("/settings");
      setPolicy({
        browser_mode: settings.browser_mode === "headless" ? "headless" : "headed",
        browser_blocked_domains: String(settings.browser_blocked_domains ?? ""),
        browser_confirm_domains: String(settings.browser_confirm_domains ?? ""),
        shopping_per_order_cap: String(settings.shopping_per_order_cap ?? "200"),
        shopping_monthly_cap: String(settings.shopping_monthly_cap ?? ""),
        shopping_default_address: String(settings.shopping_default_address ?? ""),
      });
    } catch {
      // 策略读取失败保持默认值
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

  const savePolicy = useCallback(async () => {
    setSaving(true);
    try {
      const cap = Number(policy.shopping_per_order_cap);
      const monthly = Number(policy.shopping_monthly_cap);
      await request("/settings", {
        method: "PUT",
        body: JSON.stringify({
          browser_mode: policy.browser_mode,
          browser_blocked_domains: policy.browser_blocked_domains.trim(),
          browser_confirm_domains: policy.browser_confirm_domains.trim(),
          shopping_per_order_cap: Number.isFinite(cap) && cap > 0 ? cap : 200,
          shopping_monthly_cap: Number.isFinite(monthly) && monthly > 0 ? monthly : null,
          shopping_default_address: policy.shopping_default_address.trim(),
        }),
      });
      toast.success(t("settings.browserPolicySaved", "策略已保存"));
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      toast.error(
        t("settings.browserPolicySaveFailed", "策略保存失败") + (detail ? `: ${detail}` : ""),
      );
    } finally {
      setSaving(false);
    }
  }, [policy, t]);

  const setField = (key: keyof PolicyState) => (value: string) =>
    setPolicy((prev) => ({ ...prev, [key]: value }));

  /** 执行模式即时保存：点选即 PUT——模式按钮不是表单项，等「保存策略」
   * 才持久化会让用户以为切了其实没存（实测踩坑）。 */
  const chooseMode = useCallback(
    async (mode: "headless" | "headed") => {
      setPolicy((prev) => ({ ...prev, browser_mode: mode }));
      try {
        await request("/settings", {
          method: "PUT",
          body: JSON.stringify({ browser_mode: mode }),
        });
        toast.success(
          t(
            "settings.browserModeSaved",
            mode === "headless" ? "已切无头模式（下次任务生效）" : "已切有头模式（下次任务生效）",
          ),
        );
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        toast.error(
          t("settings.browserPolicySaveFailed", "保存失败") + (detail ? `: ${detail}` : ""),
        );
      }
    },
    [t],
  );

  return (
    <div className="settings-section settings-browser">
      <h3>
        <span>{t("settings.browserChannelTitle", "调试通道与执行模式")}</span>
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
      <label className="browser-field">
        <span>{t("settings.browserMode", "执行模式")}</span>
        <div className="browser-field-row">
          <Button
            variant={policy.browser_mode === "headless" ? "primary" : "secondary"}
            onClick={() => void chooseMode("headless")}
          >
            {t("settings.browserModeHeadless", "无头（不打扰）")}
          </Button>
          <Button
            variant={policy.browser_mode === "headed" ? "primary" : "secondary"}
            onClick={() => void chooseMode("headed")}
          >
            {t("settings.browserModeHeaded", "有头（可见窗口）")}
          </Button>
        </div>
        <span className="browser-desc">
          {t(
            "settings.browserModeHint",
            "无头模式下登录/支付等人工步骤仍需切回有头完成（切换自动生效，登录态保留）。",
          )}
        </span>
      </label>
      <div>
        <Button variant="secondary" onClick={() => void setup()} disabled={launching}>
          {launching
            ? t("settings.browserLaunching", "启动中…")
            : status?.running
              ? t("settings.browserRelaunch", "重新引导启动")
              : t("settings.browserSetup", "一键启动专用浏览器")}
        </Button>
      </div>

      <details
        className="browser-policy-card"
        open={policyOpen}
        ref={policyRef}
        data-open={policyOpen ? "true" : undefined}
      >
        <summary
          className="browser-policy-summary"
          onClick={(event) => {
            event.preventDefault();
            setPolicyOpen((value) => !value);
          }}
        >
          <span className="browser-policy-title">
            {t("settings.browserPolicyTitle", "域名策略与购物护栏")}
          </span>
          {policy.browser_confirm_domains.trim() && (
            <Tag tone="success">{t("settings.browserPolicyActive", "已配置")}</Tag>
          )}
          <ChevronDown size={13} className={policyOpen ? "expanded" : ""} />
        </summary>
        <div className="browser-policy-body">
          <label className="browser-field">
            <span>{t("settings.browserBlockedDomains", "禁止导航的域名（逗号分隔）")}</span>
            <Input
              value={policy.browser_blocked_domains}
              onChange={(e) => setField("browser_blocked_domains")(e.target.value)}
              placeholder="evil.com, phishing.example"
            />
          </label>
          <label className="browser-field">
            <span>
              {t("settings.browserConfirmDomains", "变更动作需每次确认的域名（逗号分隔）")}
            </span>
            <Input
              value={policy.browser_confirm_domains}
              onChange={(e) => setField("browser_confirm_domains")(e.target.value)}
              placeholder="admin.example.com"
            />
          </label>
          <div className="browser-field-row">
            <label className="browser-field">
              <span>{t("settings.shoppingPerOrderCap", "单笔金额上限（¥）")}</span>
              <Input
                type="number"
                value={policy.shopping_per_order_cap}
                onChange={(e) => setField("shopping_per_order_cap")(e.target.value)}
              />
            </label>
            <label className="browser-field">
              <span>{t("settings.shoppingMonthlyCap", "月度上限（¥，空=不限）")}</span>
              <Input
                type="number"
                value={policy.shopping_monthly_cap}
                onChange={(e) => setField("shopping_monthly_cap")(e.target.value)}
              />
            </label>
          </div>
          <label className="browser-field">
            <span>{t("settings.shoppingDefaultAddress", "默认收货地址")}</span>
            <Input
              value={policy.shopping_default_address}
              onChange={(e) => setField("shopping_default_address")(e.target.value)}
              placeholder={t("settings.shoppingDefaultAddressHint", "结算地址不一致时在确认卡警示")}
            />
          </label>
          <div className="browser-policy-actions">
            <Button variant="primary" onClick={() => void savePolicy()} disabled={saving}>
              {saving
                ? t("settings.browserPolicySaving", "保存中…")
                : t("settings.browserPolicySave", "保存策略")}
            </Button>
          </div>
        </div>
      </details>
    </div>
  );
}
