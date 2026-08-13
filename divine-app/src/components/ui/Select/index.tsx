import { ChevronDown } from "lucide-react";
import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import "./index.less";

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  label?: string;
  placeholder?: string;
  editable?: boolean;
}

export function Select({
  value,
  onChange,
  options,
  label,
  placeholder,
  editable = false,
}: SelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});

  useEffect(() => {
    if (!open) return;
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setMenuStyle({
        position: "fixed",
        top: rect.bottom + 6,
        left: rect.left,
        width: rect.width,
      });
    }
    const closeOnOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        ref.current &&
        menuRef.current &&
        !ref.current.contains(target) &&
        !menuRef.current.contains(target)
      ) {
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

  const current = options.find((option) => option.value === value);
  const resolvedPlaceholder = placeholder ?? t("common.pleaseSelect", "请选择");

  return (
    <div className="ui-field">
      {label && <span className="ui-field-label">{label}</span>}
      <div className={`ui-select${editable ? " editable" : ""}`} ref={ref}>
        {editable ? (
          <div className="ui-select-input-wrap">
            <input
              value={value}
              placeholder={resolvedPlaceholder}
              onChange={(event) => onChange(event.target.value)}
              onFocus={() => setOpen(true)}
              aria-haspopup="listbox"
              aria-expanded={open}
            />
            <ChevronDown
              size={14}
              className={open ? "open" : ""}
              onClick={() => setOpen((value) => !value)}
            />
          </div>
        ) : (
          <button
            type="button"
            className="ui-select-trigger"
            onClick={() => setOpen((value) => !value)}
            aria-haspopup="listbox"
            aria-expanded={open}
          >
            <span>{current?.label ?? resolvedPlaceholder}</span>
            <ChevronDown size={14} className={open ? "open" : ""} />
          </button>
        )}
        {open && (
          createPortal(
            <div
              ref={menuRef}
              className="ui-select-menu"
              role="listbox"
              style={menuStyle}
            >
              {options.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={option.value === value}
                  className={`ui-select-option${
                    option.value === value ? " selected" : ""
                  }`}
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                  onMouseDown={(event) => event.preventDefault()}
                >
                  {option.label}
                </button>
              ))}
            </div>,
            document.body
          )
        )}
      </div>
    </div>
  );
}
