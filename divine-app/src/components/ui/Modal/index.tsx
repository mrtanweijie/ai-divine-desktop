import { useEffect, type ReactNode } from "react";
import "./index.less";

export interface ModalProps {
  open: boolean;
  title?: string;
  titleSuffix?: ReactNode;
  headerAction?: ReactNode;
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
  onClose,
  children,
  footer,
  width = 480,
}: ModalProps) {
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
              {titleSuffix && (
                <span className="ui-modal-title-suffix">{titleSuffix}</span>
              )}
            </h2>
            {headerAction && (
              <div className="ui-modal-header-action">{headerAction}</div>
            )}
          </div>
        )}
        <div className="ui-modal-body">{children}</div>
        {footer && <div className="ui-modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
