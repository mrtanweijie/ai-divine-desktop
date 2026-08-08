import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
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
}

export function Select({
  value,
  onChange,
  options,
  label,
  placeholder = "请选择",
}: SelectProps) {
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

  const current = options.find((option) => option.value === value);

  return (
    <div className="ui-field">
      {label && <span className="ui-field-label">{label}</span>}
      <div className="ui-select" ref={ref}>
        <button
          type="button"
          className="ui-select-trigger"
          onClick={() => setOpen((value) => !value)}
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <span>{current?.label ?? placeholder}</span>
          <ChevronDown size={14} className={open ? "open" : ""} />
        </button>
        {open && (
          <div className="ui-select-menu" role="listbox">
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
          </div>
        )}
      </div>
    </div>
  );
}
