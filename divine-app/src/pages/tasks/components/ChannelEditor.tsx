import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import type { DeliveryChannel, DeliveryConfig } from "@/types";
import "./ChannelEditor.less";

interface ChannelEditorProps {
  value: DeliveryConfig;
  onChange: (next: DeliveryConfig) => void;
}

const EMPTY_CHANNEL: DeliveryChannel = { type: "feishu", webhook_url: "" };

/**
 * 投递通道编辑器（design 027 §5.2）：多通道，每条一行卡。
 *
 * 保存时序列化为 `delivery.channels`；后端只认 `type` + `webhook_url`，
 * `sign_secret` / `at_mobiles` 是可选增强。
 */
export function ChannelEditor({ value, onChange }: ChannelEditorProps) {
  const { t } = useTranslation();
  const channels = value.channels ?? [];

  const patch = (index: number, next: Partial<DeliveryChannel>) => {
    const updated = channels.map((item, i) => (i === index ? { ...item, ...next } : item));
    onChange({ channels: updated });
  };

  const add = () => {
    onChange({ channels: [...channels, { ...EMPTY_CHANNEL }] });
  };

  const remove = (index: number) => {
    onChange({ channels: channels.filter((_, i) => i !== index) });
  };

  return (
    <div className="channel-editor">
      {channels.length === 0 && (
        <div className="channel-editor-empty">
          {t("tasks.noChannel", "未配置投递通道（任务仍会执行，只是不推送）")}
        </div>
      )}
      {channels.map((channel, index) => (
        <div className="channel-card" key={index}>
          <Flex align="center" justify="space-between" className="channel-card-head">
            <Select
              value={channel.type}
              onChange={(next) => patch(index, { type: next as DeliveryChannel["type"] })}
              options={[
                { value: "feishu", label: t("tasks.channelFeishu", "飞书") },
                { value: "wecom", label: t("tasks.channelWecom", "企业微信") },
              ]}
            />
            <Button variant="ghost" size="small" onClick={() => remove(index)}>
              {t("common.remove", "移除")}
            </Button>
          </Flex>
          <Input
            label={t("tasks.webhookUrl", "Webhook 地址")}
            value={channel.webhook_url}
            onChange={(event) => patch(index, { webhook_url: event.target.value })}
            placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
          />
          {channel.type === "feishu" && (
            <Input
              label={t("tasks.signSecret", "签名密钥（可选）")}
              type="password"
              value={channel.sign_secret ?? ""}
              onChange={(event) => patch(index, { sign_secret: event.target.value })}
            />
          )}
          {channel.type === "wecom" && (
            <Input
              label={t("tasks.atMobiles", "@ 手机号（逗号分隔，可选）")}
              value={(channel.at_mobiles ?? []).join(", ")}
              onChange={(event) =>
                patch(index, {
                  at_mobiles: event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                })
              }
            />
          )}
        </div>
      ))}
      <Button variant="secondary" size="small" onClick={add}>
        {t("tasks.addChannel", "+ 添加投递通道")}
      </Button>
    </div>
  );
}
