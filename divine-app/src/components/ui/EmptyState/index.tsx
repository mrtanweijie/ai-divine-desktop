import type { ReactNode } from "react";
import "./index.less";

interface EmptyStateProps {
  icon?: ReactNode;
  title?: string;
  description?: string;
}

export function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div className="ui-empty-state">
      {icon && <div className="ui-empty-icon">{icon}</div>}
      {title && <p className="ui-empty-title">{title}</p>}
      {description && <p className="ui-empty-description">{description}</p>}
    </div>
  );
}
