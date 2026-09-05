import { PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { isTauri } from "@/services/tauri";
import "./index.less";

interface TitleBarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onOpenSearch: () => void;
  fullscreen?: boolean;
}

export function TitleBar({
  collapsed,
  onToggleCollapse,
  onOpenSearch,
  fullscreen = false,
}: TitleBarProps) {
  const { t } = useTranslation();
  const toggleTitle = collapsed
    ? t("common.expandSessionList", "展开会话列表")
    : t("common.collapseSessionList", "收起会话列表");
  return (
    <div className={`titlebar${collapsed ? " collapsed" : ""}${fullscreen ? " fullscreen" : ""}`}>
      {!fullscreen && (
        <div className="titlebar-drag" {...(isTauri() ? { "data-tauri-drag-region": true } : {})} />
      )}
      <Flex align="center" gap={2} className="titlebar-actions">
        <Button
          variant="icon"
          size="small"
          onClick={onToggleCollapse}
          title={toggleTitle}
          aria-label={toggleTitle}
        >
          {collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
        </Button>
        {!collapsed && (
          <Button
            variant="icon"
            size="small"
            onClick={onOpenSearch}
            title={t("common.searchSessions", "搜索会话")}
            aria-label={t("common.searchSessions", "搜索会话")}
          >
            <Search size={15} />
          </Button>
        )}
      </Flex>
    </div>
  );
}
