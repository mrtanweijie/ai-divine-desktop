from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app import db  # noqa: E402
from app.schedule_utils import iso, parse_dt  # noqa: E402


def _ok(message: str, data: dict | None = None) -> None:
    print(
        json.dumps(
            {"success": True, "message": message, "data": data},
            ensure_ascii=False,
        )
    )


def _err(message: str) -> None:
    print(json.dumps({"success": False, "message": message}, ensure_ascii=False))


def _create(params: dict) -> None:
    title = str(params.get("title") or "").strip()
    start_at = str(params.get("start_at") or "")
    if not title or not start_at:
        _err("创建日程需要 title 和 start_at")
        return
    start = parse_dt(start_at)
    if start is None:
        _err(f"开始时间格式不正确: {start_at}")
        return
    end_at = params.get("end_at")
    if not end_at:
        end_at = iso(start + timedelta(hours=1))
    else:
        end = parse_dt(end_at)
        if end is None or end <= start:
            _err("结束时间必须晚于开始时间")
            return
    task_id = params.get("task_id")
    if task_id and db.get_scheduled_task(task_id) is None:
        _err("关联的定时任务不存在")
        return
    event = db.create_calendar_event(
        title=title,
        start_at=start_at,
        end_at=end_at,
        notes=str(params.get("notes") or "").strip(),
        location=str(params.get("location") or "").strip(),
        task_id=task_id,
    )
    _ok(
        f"日程已写入：{event['title']}",
        {"event": event, "events": db.list_calendar_events()},
    )


def _update(params: dict) -> None:
    event_id = str(params.get("event_id") or "")
    if not event_id or db.get_calendar_event(event_id) is None:
        _err("更新日程需要有效的 event_id")
        return
    fields: dict = {}
    for key in ("title", "start_at", "end_at", "notes", "location", "task_id"):
        if params.get(key) is not None:
            fields[key] = params[key]
    if not fields:
        _ok("没有需要更新的字段", {"event": db.get_calendar_event(event_id)})
        return
    if "start_at" in fields:
        start = parse_dt(fields["start_at"])
        if start is None:
            _err("开始时间格式不正确")
            return
        if "end_at" not in fields:
            current = db.get_calendar_event(event_id)
            if current.get("end_at"):
                end = parse_dt(current["end_at"])
                if end is None or end <= start:
                    fields["end_at"] = iso(start + timedelta(hours=1))
            else:
                fields["end_at"] = iso(start + timedelta(hours=1))
    event = db.update_calendar_event(event_id, **fields)
    _ok(f"日程已更新：{event['title']}", {"event": event})


def main() -> None:
    data = json.load(sys.stdin)
    params = data.get("params") or {}
    action = str(params.get("action") or "list")
    try:
        if action == "create":
            _create(params)
        elif action == "update":
            _update(params)
        elif action == "delete":
            event_id = str(params.get("event_id") or "")
            if not event_id or db.get_calendar_event(event_id) is None:
                _err("删除日程需要有效的 event_id")
                return
            db.delete_calendar_event(event_id)
            _ok("日程已删除", {"events": db.list_calendar_events()})
        else:
            _ok("当前日程", {"events": db.list_calendar_events()})
    except Exception as exc:  # noqa: BLE001
        _err(f"操作失败: {exc}")


if __name__ == "__main__":
    main()
