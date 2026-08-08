import type { InputHTMLAttributes } from "react";
import "./index.less";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function Input({
  label,
  error,
  className,
  id,
  ...rest
}: InputProps) {
  return (
    <label className={`ui-field${error ? " ui-field--error" : ""}`} htmlFor={id}>
      {label && <span className="ui-field-label">{label}</span>}
      <input
        id={id}
        className={`ui-input${className ? ` ${className}` : ""}`}
        {...rest}
      />
      {error && <span className="ui-field-error">{error}</span>}
    </label>
  );
}
