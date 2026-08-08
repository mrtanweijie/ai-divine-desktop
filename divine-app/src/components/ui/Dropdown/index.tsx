import {
  cloneElement,
  isValidElement,
  useEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
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
  align?: "start" | "end";
  label?: string;
}

export function Dropdown({
  trigger,
  items,
  align = "end",
  label,
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
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
  }, [open]);

  return (
    <div className="ui-dropdown" ref={ref}>
      {isValidElement(trigger)
        ? cloneElement(trigger as ReactElement, {
            onClick: () => setOpen((value) => !value),
            "aria-haspopup": "menu",
            "aria-expanded": open,
            ...(label ? { "aria-label": label } : {}),
          })
        : trigger}
      {open && (
        <div className={`ui-menu ui-menu--${align}`} role="menu">
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              className={`ui-menu-item${item.danger ? " ui-menu-item--danger" : ""}`}
              disabled={item.disabled}
              onClick={() => {
                setOpen(false);
                item.onClick?.();
              }}
            >
              {item.icon && <span className="ui-menu-icon">{item.icon}</span>}
              <span className="ui-menu-text">
                <span>{item.label}</span>
                {item.description && (
                  <small className="ui-menu-description">
                    {item.description}
                  </small>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
