import { ChevronLeft, ChevronRight, Clock3 } from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import i18next from "@/i18n";
import "./index.less";

interface DateTimePickerProps {
  value: string;
  onChange: (iso: string) => void;
  label?: string;
}

const HOURS = Array.from({ length: 24 }, (_, index) => index);
const MINUTES = Array.from({ length: 12 }, (_, index) => index * 5);

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function parseValue(value: string): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDisplay(date: Date | null): string {
  if (!date) return i18next.t("time.pickDateTime", "选择日期和时间");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate()
  )} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function DateTimePicker({
  value,
  onChange,
  label,
}: DateTimePickerProps) {
  const { t } = useTranslation();
  const resolvedLabel = label ?? t("time.label", "时间");
  const weekdays = [
    t("time.weekdayShort.sunday", "日"),
    t("time.weekdayShort.monday", "一"),
    t("time.weekdayShort.tuesday", "二"),
    t("time.weekdayShort.wednesday", "三"),
    t("time.weekdayShort.thursday", "四"),
    t("time.weekdayShort.friday", "五"),
    t("time.weekdayShort.saturday", "六"),
  ];
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const calendarRef = useRef<HTMLDivElement>(null);
  const timePanelRef = useRef<HTMLDivElement>(null);
  const hourListRef = useRef<HTMLDivElement>(null);
  const minuteListRef = useRef<HTMLDivElement>(null);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});
  const [draft, setDraft] = useState<Date | null>(parseValue(value));
  const [timeListHeight, setTimeListHeight] = useState(0);
  const [view, setView] = useState(() => {
    const date = parseValue(value) ?? new Date();
    return { year: date.getFullYear(), month: date.getMonth() };
  });

  useEffect(() => {
    if (!document.getElementById("divine-datetime-picker-portal")) {
      const portal = document.createElement("div");
      portal.id = "divine-datetime-picker-portal";
      document.body.appendChild(portal);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setDraft(parseValue(value));
    const date = parseValue(value) ?? new Date();
    setView({ year: date.getFullYear(), month: date.getMonth() });
    let frame = 0;
    if (wrapRef.current) {
      const rect = wrapRef.current.getBoundingClientRect();
      const baseStyle: CSSProperties = {
        position: "fixed",
        left: rect.left,
        width: 400,
      };
      const estimatedHeight = 360;
      const spaceBelow = window.innerHeight - rect.bottom - 6;
      const spaceAbove = rect.top - 6;
      if (spaceBelow < estimatedHeight && spaceAbove >= estimatedHeight) {
        setMenuStyle({
          ...baseStyle,
          bottom: window.innerHeight - rect.top + 6,
        });
      } else {
        setMenuStyle({ ...baseStyle, top: rect.bottom + 6 });
      }
    }
    const closeOnOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        wrapRef.current &&
        menuRef.current &&
        !wrapRef.current.contains(target) &&
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
    frame = window.requestAnimationFrame(() => {
      const scrollSelected = (list: HTMLDivElement | null) => {
        if (!list) return;
        const selected = list.querySelector(
          '[data-selected="true"]'
        ) as HTMLElement | null;
        if (selected) {
          list.scrollTop =
            selected.offsetTop - list.clientHeight / 2 + selected.clientHeight / 2;
        }
      };
      scrollSelected(hourListRef.current);
      scrollSelected(minuteListRef.current);
      const calendar = calendarRef.current;
      const timePanel = timePanelRef.current;
      if (calendar && timePanel) {
        const label = timePanel.querySelector(
          ".datetime-picker-time-col > span"
        ) as HTMLElement | null;
        const labelHeight = label?.offsetHeight ?? 16;
        setTimeListHeight(
          Math.max(80, calendar.clientHeight - labelHeight - 6)
        );
      }
    });
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open, value]);

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

  const prevMonth = () => {
    setView((current) => {
      const month = current.month - 1;
      return month < 0
        ? { year: current.year - 1, month: 11 }
        : { year: current.year, month };
    });
  };

  const nextMonth = () => {
    setView((current) => {
      const month = current.month + 1;
      return month > 11
        ? { year: current.year + 1, month: 0 }
        : { year: current.year, month };
    });
  };

  const pickDay = (day: Date) => {
    const base = draft ?? new Date();
    setDraft(
      new Date(
        day.getFullYear(),
        day.getMonth(),
        day.getDate(),
        base.getHours(),
        base.getMinutes()
      )
    );
  };

  const pickHour = (hour: number) => {
    const base = draft ?? new Date();
    setDraft(
      new Date(
        base.getFullYear(),
        base.getMonth(),
        base.getDate(),
        hour,
        base.getMinutes()
      )
    );
  };

  const pickMinute = (minute: number) => {
    const base = draft ?? new Date();
    setDraft(
      new Date(
        base.getFullYear(),
        base.getMonth(),
        base.getDate(),
        base.getHours(),
        minute
      )
    );
  };

  const confirm = () => {
    onChange(draft ? draft.toISOString() : "");
    setOpen(false);
  };

  const selected = parseValue(value);
  const today = new Date();

  return (
    <div className="ui-field">
      {resolvedLabel && <span className="ui-field-label">{resolvedLabel}</span>}
      <div className="datetime-picker" ref={wrapRef}>
        <button
          type="button"
          className="datetime-picker-trigger"
          onClick={() => setOpen((value) => !value)}
          aria-haspopup="dialog"
          aria-expanded={open}
        >
          <span>{formatDisplay(selected)}</span>
          <Clock3 size={14} />
        </button>
      </div>
      {open &&
        createPortal(
          <div
            ref={menuRef}
            className="datetime-picker-popover"
            style={menuStyle}
            role="dialog"
            aria-label={t("time.pickDateTime", "选择日期和时间")}
          >
            <div className="datetime-picker-body">
              <div ref={calendarRef} className="datetime-picker-calendar">
                <div className="datetime-picker-head">
                  <Button
                    variant="icon"
                    size="small"
                    onClick={prevMonth}
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
                    onClick={nextMonth}
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
                        onClick={() => pickDay(day)}
                      >
                        {day.getDate()}
                      </button>
                    ) : (
                      <span key={`blank-${index}`} />
                    )
                  )}
                </div>
              </div>
              <div ref={timePanelRef} className="datetime-picker-time">
                <div className="datetime-picker-time-col">
                  <span>{t("time.hourColumn", "时")}</span>
                  <div
                    ref={hourListRef}
                    className="datetime-picker-time-list"
                    style={{ height: timeListHeight || 120 }}
                  >
                    {HOURS.map((hour) => (
                      <div
                        key={hour}
                        data-selected={draft?.getHours() === hour}
                        className={`datetime-picker-time-item${
                          draft?.getHours() === hour ? " selected" : ""
                        }`}
                        onClick={() => pickHour(hour)}
                      >
                        {pad(hour)}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="datetime-picker-time-col">
                  <span>{t("time.minuteColumn", "分")}</span>
                  <div
                    ref={minuteListRef}
                    className="datetime-picker-time-list"
                    style={{ height: timeListHeight || 120 }}
                  >
                    {MINUTES.map((minute) => (
                      <div
                        key={minute}
                        data-selected={draft?.getMinutes() === minute}
                        className={`datetime-picker-time-item${
                          draft?.getMinutes() === minute ? " selected" : ""
                        }`}
                        onClick={() => pickMinute(minute)}
                      >
                        {pad(minute)}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            <div className="datetime-picker-footer">
              <Button
                size="small"
                variant="ghost"
                onClick={() => setDraft(new Date())}
              >
                {t("common.now", "现在")}
              </Button>
              <Button size="small" onClick={confirm}>
                {t("common.confirm", "确定")}
              </Button>
            </div>
          </div>,
          document.getElementById("divine-datetime-picker-portal") ??
            document.body
        )}
    </div>
  );
}
