"""定时任务 handler 共用工具（design 027）：审批模式、最终答案提取、执行记录。"""

from __future__ import annotations


def test_final_answer_takes_last_assistant():
    from app.agent.tasks.common import final_answer_from_history

    history = [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": "第一轮"},
        {"role": "assistant", "content": "最终答案"},
    ]
    assert final_answer_from_history(history) == "最终答案"


def test_final_answer_skips_trailing_tool_and_empty():
    """Agent 尾巴常是 tool 结果或空 assistant —— 都要跳过。"""
    from app.agent.tasks.common import final_answer_from_history

    history = [
        {"role": "assistant", "content": "真正的答案"},
        {"role": "tool", "content": "tool result"},
        {"role": "assistant", "content": "   "},
    ]
    assert final_answer_from_history(history) == "真正的答案"


def test_final_answer_empty_when_no_assistant():
    from app.agent.tasks.common import final_answer_from_history

    assert final_answer_from_history([]) == ""
    assert final_answer_from_history([{"role": "user", "content": "x"}]) == ""


def test_legacy_types_forced_full_access():
    """agent / monitor 与改前一致：强制 full + direct。"""
    from app.agent.tasks.common import _approval_and_plan

    session = {"approval_mode": "ask", "plan_mode": "ask"}
    assert _approval_and_plan({"task_type": "agent"}, session) == ("full", "direct")
    assert _approval_and_plan({"task_type": "monitor"}, session) == (
        "full",
        "direct",
    )


def test_new_types_respect_session_unless_full_access():
    from app.agent.tasks.common import _approval_and_plan

    session = {"approval_mode": "ask", "plan_mode": "ask"}
    assert _approval_and_plan({"task_type": "webhook"}, session) == ("ask", "ask")
    # 开了开关就等同旧行为
    assert _approval_and_plan(
        {"task_type": "webhook", "allow_full_access": True}, session
    ) == ("full", "direct")


def test_run_recorder_lifecycle(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "rec.db"))
    from app import db

    db.init_db()
    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t", session_id=session["id"], task_type="webhook"
    )

    from app.agent.tasks.common import RunRecorder

    recorder = RunRecorder(task["id"])
    recorder.start()
    recorder.set_output("产出")
    recorder.finish("succeeded")

    run = db.list_runs_for_task(task["id"])[0]
    assert run["status"] == "succeeded"
    assert run["output"] == "产出"


def test_run_recorder_methods_before_start_are_safe(monkeypatch, tmp_path):
    """handler 出错时可能还没 start()；这些方法必须不炸。"""
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "rec2.db"))
    from app.agent.tasks.common import RunRecorder

    recorder = RunRecorder("no-such-task")
    recorder.set_output("x")  # 无 run → 静默
    recorder.finish("succeeded")
    recorder.fail("e")
    recorder.skip("r")
