// Month calendar grid used inside the DateTimePicker popover.
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { sameDay } from "./dateTimeUtils";

interface CalendarPanelProps {
  view: { year: number; month: number };
  draft: Date | null;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onPickDay: (day: Date) => void;
}

export function CalendarPanel({
  view,
  draft,
  onPrevMonth,
  onNextMonth,
  onPickDay,
}: CalendarPanelProps) {
  const { t } = useTranslation();
  const weekdays = [
    t("time.weekdayShort.sunday", "日"),
    t("time.weekdayShort.monday", "一"),
    t("time.weekdayShort.tuesday", "二"),
    t("time.weekdayShort.wednesday", "三"),
    t("time.weekdayShort.thursday", "四"),
    t("time.weekdayShort.friday", "五"),
    t("time.weekdayShort.saturday", "六"),
  ];

  const days = useMemo(() => {
    const first = new Date(view.year, view.month, 1);
    const count = new Date(view.year, view.month + 1, 0).getDate();
    const cells: (Date | null)[] = [];
    for (let index = 0; index < first.getDay(); index++) cells.push(null);
    for (let day = 1; day <= count; day++) {
      cells.push(new Date(view.year, view.month, day));
    }
    return cells;
  }, [view]);

  const today = new Date();

  return (
    <div className="datetime-picker-calendar">
      <div className="datetime-picker-head">
        <Button
          variant="icon"
          size="small"
          onClick={onPrevMonth}
          title={t("time.previousMonth", "上个月")}
          aria-label={t("time.previousMonth", "上个月")}
        >
          <ChevronLeft size={14} />
        </Button>
        <span className="datetime-picker-title">
          {t("time.monthTitle", "{{year}}年{{month}}月", {
            year: view.year,
            month: view.month + 1,
          })}
        </span>
        <Button
          variant="icon"
          size="small"
          onClick={onNextMonth}
          title={t("time.nextMonth", "下个月")}
          aria-label={t("time.nextMonth", "下个月")}
        >
          <ChevronRight size={14} />
        </Button>
      </div>
      <div className="datetime-picker-weekdays">
        {weekdays.map((weekday) => (
          <span key={weekday}>{weekday}</span>
        ))}
      </div>
      <div className="datetime-picker-days">
        {days.map((day, index) =>
          day ? (
            <button
              key={`${day.getFullYear()}-${day.getMonth()}-${day.getDate()}`}
              type="button"
              className={`datetime-picker-day${
                draft && sameDay(draft, day) ? " selected" : ""
              }${sameDay(today, day) ? " today" : ""}`}
              onClick={() => onPickDay(day)}
            >
              {day.getDate()}
            </button>
          ) : (
            <span key={`blank-${index}`} />
          )
        )}
      </div>
    </div>
  );
}
