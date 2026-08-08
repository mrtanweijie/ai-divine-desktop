import { forwardRef, type TextareaHTMLAttributes } from "react";
import "./index.less";

export interface TextAreaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(
  function TextArea({ label, error, className, id, ...rest }, ref) {
    return (
      <label
        className={`ui-field${error ? " ui-field--error" : ""}`}
        htmlFor={id}
      >
        {label && <span className="ui-field-label">{label}</span>}
        <textarea
          ref={ref}
          id={id}
          className={`ui-textarea${className ? ` ${className}` : ""}`}
          {...rest}
        />
        {error && <span className="ui-field-error">{error}</span>}
      </label>
    );
  }
);
