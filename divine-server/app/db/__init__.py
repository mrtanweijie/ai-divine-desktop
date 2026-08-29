"""SQLite persistence layer for projects, sessions, messages, todos, and tasks.

Modules are split by domain; this package re-exports the repository functions
so existing ``from app import db; db.list_projects()`` calls keep working.
"""

from . import (
    calendar_events,
    history,
    memories,
    messages,
    migrations,
    projects,
    scheduled_tasks,
    sessions,
    summaries,
    todos,
    tool_runs,
)
from .calendar_events import (
    create_calendar_event,
    delete_calendar_event,
    get_calendar_event,
    list_calendar_events,
    update_calendar_event,
)
from .connection import (
    _connect,
    close_thread_conn,
    get_conn,
    _json,
    _new_id,
    _now,
)
from .history import history_for_model, load_session, load_session_page
from .messages import (
    add_message,
    add_message_part,
    clear_messages,
    get_message,
    list_messages,
    update_choice_state,
)
from .memories import (
    forget_memory,
    forget_memory_by_content,
    list_active_memories,
    save_memory,
    search_memories,
)
from .migrations import SCHEMA, init_db
from .projects import (
    create_project,
    default_project,
    delete_project,
    get_project,
    list_projects,
    pin_project,
    reorder_projects,
    update_project,
    update_project_order,
)
from .scheduled_tasks import (
    create_scheduled_task,
    delete_scheduled_task,
    get_scheduled_task,
    list_scheduled_tasks,
    pause_tasks_for_session,
    update_scheduled_task,
)
from .sessions import (
    create_session,
    delete_session,
    get_session,
    list_sessions,
    search_sessions,
    session_workspace,
    touch_session,
    update_session,
)
from .summaries import delete_summary, get_summary, save_summary
from .todos import list_todos, replace_todos, update_todo_status
from .tool_runs import (
    add_tool_run,
    get_tool_run,
    list_message_parts,
    list_tool_runs,
    recent_tool_runs,
    save_tool_turn,
    update_tool_run,
)
from .usage import save_token_usage, token_usage_totals
