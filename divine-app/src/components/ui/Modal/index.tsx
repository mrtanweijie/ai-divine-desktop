import { useEffect, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import "./index.less";

export interface ModalProps {
  open: boolean;
  title?: string;
  titleSuffix?: ReactNode;
  /** 标题栏右侧的自定义操作（会排在内置关闭按钮之前） */
  headerAction?: ReactNode;
  /**
   * 右上角内置关闭按钮，默认显示。
   *
   * 统一由 Modal 渲染，避免各弹窗自己塞一个导致图标/尺寸/文案不一致。
   * 需要「必须做出选择才能关闭」的场景传 `showClose={false}`。
   */
  showClose?: boolean;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number | string;
}

export function Modal({
  open,
  title,
  titleSuffix,
  headerAction,
  showClose = true,
  onClose,
  children,
  footer,
  width = 480,
}: ModalProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="ui-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="ui-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={{ width }}
      >
        {title && (
          <div className="ui-modal-header">
            <h2>
              {title}
              {titleSuffix && <span className="ui-modal-title-suffix">{titleSuffix}</span>}
            </h2>
            {(headerAction || showClose) && (
              <div className="ui-modal-header-action">
                {headerAction}
                {showClose && (
                  <Button
                    variant="icon"
                    size="small"
                    onClick={onClose}
                    aria-label={t("common.close", "关闭")}
                    title={t("common.close", "关闭")}
                  >
                    <X size={16} />
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
        <div className="ui-modal-body">{children}</div>
        {footer && <div className="ui-modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
