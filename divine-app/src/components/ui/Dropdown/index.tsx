import {
  cloneElement,
  isValidElement,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactElement,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import "./index.less";

export interface DropdownItem {
  key: string;
  label: string;
  icon?: ReactNode;
  description?: string;
  danger?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}

interface DropdownProps {
  trigger: ReactNode;
  items: DropdownItem[];
  align?: "start" | "center" | "end";
  direction?: "below" | "above";
  label?: string;
  openOn?: "click" | "hover" | "both";
}

type DropdownTriggerProps = {
  onClick?: () => void;
  "aria-haspopup"?: string;
  "aria-expanded"?: boolean;
  "aria-label"?: string;
};

export function Dropdown({
  trigger,
  items,
  align = "end",
  direction = "below",
  label,
  openOn = "click",
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});
  const ref = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<number | null>(null);
  const supportsHover = openOn === "hover" || openOn === "both";

  const cancelClose = () => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  const openMenu = () => {
    cancelClose();
    setOpen(true);
  };

  const scheduleClose = () => {
    cancelClose();
    closeTimer.current = window.setTimeout(() => {
      setOpen(false);
    }, 180);
  };

  useEffect(() => {
    if (!open) return;
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect();
      const base: CSSProperties = {
        position: "fixed",
      };
      const vertical =
        direction === "above"
          ? { top: rect.top - 6, transform: "translateY(-100%)" }
          : { top: rect.bottom + 6 };
      if (align === "start") {
        setMenuStyle({
          ...base,
          ...vertical,
          left: rect.left,
          ...(direction === "above" ? { transform: "translate(0, -100%)" } : {}),
        });
      } else if (align === "end") {
        setMenuStyle({
          ...base,
          ...vertical,
          left: rect.right,
          transform: direction === "above" ? "translate(-100%, -100%)" : "translateX(-100%)",
        });
      } else {
        setMenuStyle({
          ...base,
          ...vertical,
          left: rect.left + rect.width / 2,
          transform: direction === "above" ? "translate(-50%, -100%)" : "translateX(-50%)",
        });
      }
    }
    const closeOnOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        const target = event.target as HTMLElement | null;
        if (!target?.closest(".ui-menu")) {
          setOpen(false);
        }
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [align, direction, open]);

  useEffect(() => {
    return () => {
      if (closeTimer.current !== null) {
        window.clearTimeout(closeTimer.current);
      }
    };
  }, []);

  return (
    <div
      className={`ui-dropdown${open ? " open" : ""}`}
      ref={ref}
      onMouseEnter={supportsHover ? openMenu : undefined}
      onMouseLeave={supportsHover ? scheduleClose : undefined}
    >
      {isValidElement(trigger)
        ? cloneElement(trigger as ReactElement<DropdownTriggerProps>, {
            onClick: () => setOpen((value) => !value),
            "aria-haspopup": "menu",
            "aria-expanded": open,
            ...(label ? { "aria-label": label } : {}),
          })
        : trigger}
      {open &&
        createPortal(
          <div
            className={`ui-menu ui-menu--${align}`}
            style={menuStyle}
            role="menu"
            onMouseEnter={supportsHover ? cancelClose : undefined}
            onMouseLeave={supportsHover ? scheduleClose : undefined}
          >
            {items.map((item) => (
              <div
                key={item.key}
                role="menuitem"
                tabIndex={item.disabled ? -1 : 0}
                aria-disabled={item.disabled || undefined}
                className={`ui-menu-item${item.danger ? " ui-menu-item--danger" : ""}${item.disabled ? " ui-menu-item--disabled" : ""}`}
                onClick={() => {
                  if (item.disabled) return;
                  setOpen(false);
                  item.onClick?.();
                }}
                onKeyDown={(event) => {
                  if (item.disabled) return;
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setOpen(false);
                    item.onClick?.();
                  }
                }}
              >
                {item.icon && <span className="ui-menu-icon">{item.icon}</span>}
                <span className="ui-menu-text">
                  <span>{item.label}</span>
                  {item.description && (
                    <small className="ui-menu-description">{item.description}</small>
                  )}
                </span>
              </div>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}
