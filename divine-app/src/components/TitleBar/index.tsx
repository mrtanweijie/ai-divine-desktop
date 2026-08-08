import { PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Flex } from "@/components/ui/Flex";
import { isMacosDesktop } from "@/services/tauri";
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
  return (
    <div
      className={`titlebar${collapsed ? " collapsed" : ""}${
        fullscreen ? " fullscreen" : ""
      }`}
    >
      {!fullscreen && (
        <div
          className="titlebar-drag"
          {...(isMacosDesktop() ? { "data-tauri-drag-region": true } : {})}
        />
      )}
      <Flex align="center" gap={2} className="titlebar-actions">
        <Button
          variant="icon"
          size="small"
          onClick={onToggleCollapse}
          title={collapsed ? "展开会话列表" : "收起会话列表"}
          aria-label={collapsed ? "展开会话列表" : "收起会话列表"}
        >
          {collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
        </Button>
        {!collapsed && (
          <Button
            variant="icon"
            size="small"
            onClick={onOpenSearch}
            title="搜索会话"
            aria-label="搜索会话"
          >
            <Search size={15} />
          </Button>
        )}
      </Flex>
    </div>
  );
}
