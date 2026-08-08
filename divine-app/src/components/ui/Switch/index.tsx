import "./index.less";

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  disabled?: boolean;
  id?: string;
}

export function Switch({
  checked,
  onChange,
  label,
  disabled,
  id,
}: SwitchProps) {
  return (
    <label className="ui-switch" htmlFor={id}>
      {label && <span className="ui-switch-label">{label}</span>}
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="ui-switch-input"
      />
      <span className="ui-switch-track" aria-hidden="true">
        <span className="ui-switch-thumb" />
      </span>
    </label>
  );
}
