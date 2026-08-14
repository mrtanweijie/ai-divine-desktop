// Prebuilt task suggestion cards shown when no search filter is active.
import { Check, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

export interface TaskSuggestion {
  key: string;
  title: string;
  schedule: string;
  description: string;
  frequency: "once" | "interval" | "daily" | "weekly" | "monthly";
  run_hour: number;
  run_minute: number;
  days_of_week: number[];
}

interface SuggestionCardsProps {
  suggestions: TaskSuggestion[];
  creatingSuggestion: string | null;
  createdSuggestion: string | null;
  onCreate: (suggestion: TaskSuggestion) => void;
}

export function SuggestionCards({
  suggestions,
  creatingSuggestion,
  createdSuggestion,
  onCreate,
}: SuggestionCardsProps) {
  const { t } = useTranslation();
  return (
    <section className="suggestion-section">
      <h2>{t("tasks.suggestions", "建议")}</h2>
      <div className="suggestion-grid">
        {suggestions.map((suggestion) => (
          <div
            key={suggestion.key}
            className={`suggestion-card${
              creatingSuggestion === suggestion.key ? " creating" : ""
            }`}
            role="button"
            tabIndex={creatingSuggestion ? -1 : 0}
            aria-disabled={creatingSuggestion !== null}
            onClick={() => onCreate(suggestion)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                onCreate(suggestion);
                event.currentTarget.blur();
              }
            }}
          >
            <div className="suggestion-head">
              <span className="suggestion-title">{suggestion.title}</span>
              {creatingSuggestion === suggestion.key ? (
                <span className="suggestion-state">
                  {t("tasks.creating", "创建中...")}
                </span>
              ) : createdSuggestion === suggestion.key ? (
                <span className="suggestion-state created">
                  <Check size={13} />
                  {t("tasks.createdBadge", "已创建")}
                </span>
              ) : (
                <ChevronRight size={14} />
              )}
            </div>
            <div className="suggestion-schedule">{suggestion.schedule}</div>
            <div className="suggestion-desc">{suggestion.description}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
