import type { InputHTMLAttributes, ReactNode } from "react";
import "./index.less";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  action?: ReactNode;
}

export function Input({
  label,
  error,
  className,
  id,
  action,
  ...rest
}: InputProps) {
  return (
    <label className={`ui-field${error ? " ui-field--error" : ""}`} htmlFor={id}>
      {label && <span className="ui-field-label">{label}</span>}
      <div className={`ui-input-wrap${action ? " has-action" : ""}`}>
        <input
          id={id}
          className={`ui-input${className ? ` ${className}` : ""}`}
          {...rest}
        />
        {action && <span className="ui-input-action">{action}</span>}
      </div>
      {error && <span className="ui-field-error">{error}</span>}
    </label>
  );
}
