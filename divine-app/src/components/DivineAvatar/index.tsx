interface DivineAvatarProps {
  size?: number;
  className?: string;
}

export function DivineAvatar({ size, className }: DivineAvatarProps) {
  const iconSize = size ? Math.round(size * 0.55) : undefined;
  return (
    <span
      className={`divine-avatar${className ? ` ${className}` : ""}`}
      aria-hidden="true"
      style={size ? { width: size, height: size } : undefined}
    >
      <svg
        viewBox="0 0 16 16"
        xmlns="http://www.w3.org/2000/svg"
        style={iconSize ? { width: iconSize, height: iconSize } : undefined}
      >
        <path d="M8 2.5 L14 13.5 H2 Z" fill="none" strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    </span>
  );
}
