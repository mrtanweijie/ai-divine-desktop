"""故障诊断层测试（design 026 P1）。

覆盖：三类解析器 / 指纹稳定性与区分度 / 业务帧过滤 / 输出预算与截断 /
畸形输入不炸 / run_tests 的 trace 字段 / execution.py 的 [诊断] 回灌接线。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from app.tools.diagnostics import (
    attach_traces,
    compute_fingerprint,
    diagnose_tool_output,
    format_failure_block,
    parse_failures,
    parse_node_stack,
    parse_pytest_short,
    parse_python_traceback,
)

# --- 夹具：一个带真实源码行的迷你项目 ---------------------------------------

_AUTH_PY = (
    "from app import store\n"
    "\n"
    "\n"
    "def verify(token):\n"
    "    return store.get_by_id(token)\n"
)
_STORE_PY = (
    "STORE = {}\n"
    "\n"
    "\n"
    "def get_by_id(key):\n"
    "    return STORE[key]\n"
)
_TEST_API_PY = (
    "from app import auth\n"
    "\n"
    "\n"
    "def test_login():\n"
    "    assert auth.verify('abc') == 'ok'\n"
)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "auth.py").write_text(_AUTH_PY, encoding="utf-8")
    (tmp_path / "app" / "store.py").write_text(_STORE_PY, encoding="utf-8")
    (tmp_path / "tests" / "test_api.py").write_text(_TEST_API_PY, encoding="utf-8")
    return tmp_path


# pytest --tb=short 的真实输出形状（run_tests 用的就是这组参数）。
_PYTEST_SHORT = (
    "FF.                                                                      [100%]\n"
    "=================================== FAILURES ===================================\n"
    "__________________________________ test_login __________________________________\n"
    "tests/test_api.py:5: in test_login\n"
    "    assert auth.verify('abc') == 'ok'\n"
    "app/auth.py:5: in verify\n"
    "    return store.get_by_id(token)\n"
    "app/store.py:5: in get_by_id\n"
    "    return STORE[key]\n"
    "E   KeyError: 'abc'\n"
    "=========================== short test summary info ============================\n"
    "FAILED tests/test_api.py::test_login - KeyError: 'abc'\n"
    "1 failed, 1 passed in 0.25s\n"
)

# pytest 默认 tb=long：帧行没有 `in func`，首/末帧尾部还挂着别的东西。
_PYTEST_LONG = (
    "__________________________________ test_login __________________________________\n"
    "\n"
    "    def test_login():\n"
    ">       assert auth.verify('abc') == 'ok'\n"
    "               ^^^^^^^^^^^^^^^^^^^^^^^^\n"
    "\n"
    "tests/test_api.py:5: \n"
    "_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ \n"
    "app/auth.py:5: in verify\n"
    "    return store.get_by_id(token)\n"
    "           ^^^^^^^^^^^^^^^^^^^\n"
    "_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ \n"
    "\n"
    "key = 'abc'\n"
    "\n"
    "    def get_by_id(key):\n"
    ">       return STORE[key]\n"
    "               ^^^^^^^^^^\n"
    "E       KeyError: 'abc'\n"
    "\n"
    "app/store.py:5: KeyError\n"
)


# --- pytest 短格式 -----------------------------------------------------------


def test_pytest_short_frames_and_anchor(project: Path):
    reports = parse_pytest_short(_PYTEST_SHORT, project)
    assert len(reports) == 1
    report = reports[0]
    assert report.kind == "python_traceback"
    assert report.exception == "KeyError"
    assert report.message == "'abc'"
    assert report.node == "test_login"
    assert [f.file for f in report.frames] == [
        "tests/test_api.py",
        "app/auth.py",
        "app/store.py",
    ]
    assert [f.line for f in report.frames] == [5, 5, 5]
    # 测试帧算 user_code，但不做业务帧——否则同一 bug 换个测试就换指纹。
    assert report.frames[0].is_user_code is True
    assert report.frames[0].is_business is False
    assert report.frames[1].is_business is True
    # 源码行由诊断层自己读文件补齐，不依赖输出里是否打印。
    assert report.frames[1].code == "return store.get_by_id(token)"
    assert report.anchor() is report.frames[1]


def test_pytest_short_multiple_blocks(project: Path):
    text = _PYTEST_SHORT + (
        "_________________________________ test_second _________________________________\n"
        "tests/test_api.py:9: in test_second\n"
        "    raise ValueError('boom two')\n"
        "E   ValueError: boom two\n"
    )
    reports = parse_pytest_short(text, project)
    assert [r.exception for r in reports] == ["KeyError", "ValueError"]
    assert reports[1].message == "boom two"


def test_pytest_short_bare_assert_is_assertion_error(project: Path):
    text = (
        "_____________________________ test_plain_assert ______________________________\n"
        "tests/test_api.py:5: in test_plain_assert\n"
        "    assert 1 == 2\n"
        "E   assert 1 == 2\n"
    )
    reports = parse_pytest_short(text, project)
    assert len(reports) == 1
    assert reports[0].exception == "AssertionError"


def test_pytest_short_collection_error(project: Path):
    text = (
        "______________________ ERROR collecting tests/test_api.py ______________________\n"
        "ImportError while importing test module.\n"
        "Traceback:\n"
        "tests/test_api.py:1: in <module>\n"
        "    from app import auth\n"
        "app/auth.py:1: in <module>\n"
        "    from app import store\n"
        "E   ImportError: cannot import name 'store'\n"
    )
    reports = parse_pytest_short(text, project)
    assert len(reports) == 1
    assert reports[0].exception == "ImportError"
    assert reports[0].anchor().file == "app/auth.py"


# --- 完整 traceback ----------------------------------------------------------


def test_python_traceback_full(project: Path):
    text = (
        "Traceback (most recent call last):\n"
        '  File "app/auth.py", line 5, in verify\n'
        "    return store.get_by_id(token)\n"
        '  File "app/store.py", line 5, in get_by_id\n'
        "    return STORE[key]\n"
        "KeyError: 'abc'\n"
    )
    reports = parse_python_traceback(text, project)
    assert len(reports) == 1
    assert reports[0].exception == "KeyError"
    assert [f.func for f in reports[0].frames] == ["verify", "get_by_id"]
    assert reports[0].anchor().file == "app/auth.py"


def test_python_traceback_nested_keeps_original_cause(project: Path):
    text = (
        "Traceback (most recent call last):\n"
        '  File "app/store.py", line 5, in get_by_id\n'
        "    return STORE[key]\n"
        "KeyError: 'abc'\n"
        "\n"
        "During handling of the above exception, another exception occurred:\n"
        "\n"
        "Traceback (most recent call last):\n"
        '  File "app/auth.py", line 5, in verify\n'
        "    raise RuntimeError('wrapped')\n"
        "RuntimeError: wrapped\n"
    )
    reports = parse_python_traceback(text, project)
    # 首个 traceback 是根因，模型最该先看它。
    assert [r.exception for r in reports] == ["KeyError", "RuntimeError"]


def test_python_traceback_exception_group(project: Path):
    text = (
        "  + Exception Group Traceback (most recent call last):\n"
        '  |   File "app/auth.py", line 5, in verify\n'
        "  |     raise ExceptionGroup('boom', [ValueError('a')])\n"
        "  | ExceptionGroup: boom (1 sub-exception)\n"
        "  +-+---------------- 1 ----------------\n"
        "    | Traceback (most recent call last):\n"
        '    |   File "app/store.py", line 5, in get_by_id\n'
        "    |     raise ValueError('a')\n"
        "    | ValueError: a\n"
        "    +------------------------------------\n"
    )
    reports = parse_python_traceback(text, project)
    assert [r.exception for r in reports] == ["ExceptionGroup", "ValueError"]
    # 装饰字符 `|` / `+` 不能挡住帧解析。
    assert reports[0].frames[0].file == "app/auth.py"


def test_truncated_traceback_yields_nothing(project: Path):
    text = (
        "Traceback (most recent call last):\n"
        '  File "app/auth.py", line 5, in verify\n'
        "    return store.get_by_id(token)\n"
    )
    assert parse_python_traceback(text, project) == []


# --- Node 栈 -----------------------------------------------------------------


def test_parse_node_stack_jest(project: Path):
    text = (
        "TypeError: Cannot read properties of undefined (reading 'id')\n"
        "    at getUser (/src/user.ts:10:15)\n"
        "    at Object.<anonymous> (/src/index.ts:5:3)\n"
    )
    reports = parse_node_stack(text, project)
    assert len(reports) == 1
    assert reports[0].kind == "node_stack"
    assert reports[0].exception == "TypeError"
    assert reports[0].frames[0].func == "getUser"
    assert reports[0].frames[0].line == 10


def test_node_internal_scheme_path_is_not_user_code(project: Path):
    """`node:internal/...` 不是文件路径，绝不能被当成工作区内的相对路径。"""
    text = (
        "TypeError: boom\n"
        "    at processTicksAndRejections (node:internal/process/task_queues:95:5)\n"
    )
    reports = parse_node_stack(text, project)
    assert len(reports) == 1
    assert reports[0].frames[0].is_user_code is False
    assert reports[0].frames[0].is_business is False
    assert reports[0].fingerprint == compute_fingerprint("TypeError", [])


# --- 业务帧过滤与依赖帧 ------------------------------------------------------


def test_dependency_frames_are_not_user_code(project: Path):
    text = (
        "Traceback (most recent call last):\n"
        '  File "app/auth.py", line 5, in verify\n'
        "    return store.get_by_id(token)\n"
        '  File "/x/site-packages/httpx/_client.py", line 123, in send\n'
        "    return self._send(request)\n"
        "httpx.ConnectError: connection refused\n"
    )
    reports = parse_failures(text, project)
    assert len(reports) == 1
    frames = reports[0].frames
    assert frames[0].is_user_code is True
    assert frames[1].is_user_code is False
    assert reports[0].anchor() is frames[0]


def test_dependency_only_report_falls_back_to_no_user_frame(project: Path):
    text = (
        "Traceback (most recent call last):\n"
        '  File "/x/site-packages/httpx/_client.py", line 123, in send\n'
        "    return self._send(request)\n"
        "httpx.ConnectError: connection refused\n"
    )
    reports = parse_failures(text, project)
    assert len(reports) == 1
    assert reports[0].anchor() is None
    assert reports[0].fingerprint == compute_fingerprint("httpx.ConnectError", [])
    block = format_failure_block(reports, project)
    assert "依赖内部" in block


def test_relative_paths_resolve_against_workspace_not_cwd(project: Path):
    """服务进程 CWD 与工作区无关：相对路径必须按 workspace 解析。"""
    assert Path.cwd() != project
    reports = parse_pytest_short(_PYTEST_SHORT, project)
    assert reports[0].frames[1].is_user_code is True


# --- 指纹 --------------------------------------------------------------------


def test_fingerprint_ignores_message_drift(project: Path):
    """消息里的变量值不该让同一个 bug 的指纹漂移。"""
    first = parse_pytest_short(_PYTEST_SHORT, project)[0]
    drifted = _PYTEST_SHORT.replace("KeyError: 'abc'", "KeyError: 'user_id'")
    second = parse_pytest_short(drifted, project)[0]
    assert first.fingerprint == second.fingerprint


def test_fingerprint_differs_on_different_frame(project: Path):
    first = parse_pytest_short(_PYTEST_SHORT, project)[0]
    moved = _PYTEST_SHORT.replace("app/auth.py:5", "app/auth.py:99")
    second = parse_pytest_short(moved, project)[0]
    assert first.fingerprint != second.fingerprint


def test_fingerprint_differs_on_different_exception(project: Path):
    first = parse_pytest_short(_PYTEST_SHORT, project)[0]
    other = _PYTEST_SHORT.replace("KeyError: 'abc'", "TypeError: 'abc'")
    second = parse_pytest_short(other, project)[0]
    assert first.fingerprint != second.fingerprint


def test_fingerprint_stable_across_tb_formats(project: Path):
    """tb=short 与 tb=long 描述同一次失败，指纹必须一致——否则刹车计数会分裂。"""
    short = parse_pytest_short(_PYTEST_SHORT, project)[0]
    long = parse_pytest_short(_PYTEST_LONG, project)[0]
    assert short.exception == long.exception
    assert short.fingerprint == long.fingerprint


def test_fingerprint_is_twelve_hex_chars(project: Path):
    report = parse_pytest_short(_PYTEST_SHORT, project)[0]
    assert len(report.fingerprint) == 12
    assert all(c in "0123456789abcdef" for c in report.fingerprint)


# --- 输出预算 ----------------------------------------------------------------


def test_frames_capped_but_business_frames_survive(project: Path):
    lines = ["Traceback (most recent call last):"]
    for index in range(6):
        lines.append(
            f'  File "/x/site-packages/dep{index}/m.py", line {index + 1}, in dep{index}'
        )
        lines.append(f"    return dep{index}()")
    for index in range(6):
        lines.append(f'  File "app/store.py", line {index + 1}, in biz{index}')
        lines.append(f"    return biz{index}()")
    lines.append("RuntimeError: too deep")
    report = parse_failures("\n".join(lines), project)[0]
    assert len(report.frames) <= 8
    assert sum(1 for f in report.frames if f.is_business) == 6


def test_block_truncated_to_budget():
    """帧数已被 _MAX_FRAMES 限住，超预算只可能来自超长路径/源码行——直接构造验护栏。"""
    from app.tools.diagnostics import FailureReport, Frame

    frames = [
        Frame(
            file="deep/" * 60 + f"mod{index}.py",
            line=index + 1,
            func="f" * 80,
            code="y" * 200,
            is_user_code=True,
            is_business=True,
        )
        for index in range(8)
    ]
    report = FailureReport(
        kind="python_traceback",
        exception="RuntimeError",
        message="boom",
        frames=frames,
        fingerprint="a" * 12,
    )
    block = format_failure_block([report])
    assert len(block) <= 2000
    assert "已截断" in block


def test_block_lists_frames_and_guidance(project: Path):
    block = format_failure_block(
        parse_pytest_short(_PYTEST_SHORT, project), project
    )
    assert block.startswith("[诊断]")
    assert "frames:" in block
    assert "指纹" not in block  # 计数由中间件注入，解析层不猜
    assert "fingerprint:" in block
    assert "read_file app/auth.py" in block
    assert "不要重新全仓 grep" in block


# --- 畸形输入 ----------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "just some text\n",
        "exit code 1\n",
        "Traceback (most recent call last):\n",
        "FAILED tests/a.py::test_x - AssertionError: nope\n",
        "\x00\x01 binary junk \xff\n",
        "E   KeyError: 'x'\n",
    ],
)
def test_malformed_input_never_raises(project: Path, text: str):
    assert parse_failures(text, project) == []
    assert diagnose_tool_output(text, project) == ""


def test_diagnose_tool_output_returns_block_or_empty(project: Path):
    assert diagnose_tool_output(_PYTEST_SHORT, project, "pytest").startswith(
        "[诊断]"
    )
    assert diagnose_tool_output("all good", project) == ""


def test_diagnose_tool_output_survives_parser_crash(monkeypatch, project: Path):
    """解析层内部炸了也不能把一次工具调用变成失败。"""
    import app.tools.diagnostics as diag

    def _boom(*args, **kwargs):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(diag, "parse_failures", _boom)
    assert diag.diagnose_tool_output(_PYTEST_SHORT, project) == ""


# --- run_tests 的 trace 字段 -------------------------------------------------


def test_attach_traces_matches_by_node_name(project: Path):
    reports = parse_pytest_short(_PYTEST_SHORT, project)
    failures = [
        {"kind": "failed", "test": "tests/test_a.py::test_other", "message": "x"},
        {
            "kind": "failed",
            "test": "tests/test_api.py::test_login",
            "message": "KeyError: 'abc'",
        },
    ]
    enriched = attach_traces(failures, reports)
    # 按名精确命中的那一项必须拿到报告，哪怕它排在后面——顺序回退不能抢跑。
    assert enriched[1]["trace"]["exception"] == "KeyError"
    assert enriched[1]["trace"]["fingerprint"] == reports[0].fingerprint
    # 报告只有一份且已被按名认领，匹配不上的项保持原样。
    assert "trace" not in enriched[0]
    # 原始项不被就地修改。
    assert "trace" not in failures[1]


def test_attach_traces_falls_back_positionally(project: Path):
    reports = parse_pytest_short(
        _PYTEST_SHORT
        + (
            "_________________________________ test_second _________________________________\n"
            "tests/test_api.py:9: in test_second\n"
            "    raise ValueError('boom two')\n"
            "E   ValueError: boom two\n"
        ),
        project,
    )
    # 没有 test 字段（如 jest 的失败项）时按出现顺序一一对应。
    failures = [
        {"kind": "failed", "message": "first"},
        {"kind": "failed", "message": "second"},
    ]
    enriched = attach_traces(failures, reports)
    assert enriched[0]["trace"]["exception"] == "KeyError"
    assert enriched[1]["trace"]["exception"] == "ValueError"


def test_attach_traces_without_reports_is_noop():
    failures = [{"kind": "failed", "test": "t", "message": "m"}]
    assert attach_traces(failures, []) is failures


# --- execution.py 回灌接线 ---------------------------------------------------


class _StubRuntime:
    """`_handle_adapter_call` 只用到 runtime 的这三个成员。"""

    def __init__(self) -> None:
        self.tool_call_id = "call_diag"
        self.events: list[dict] = []
        self.state = {"messages": []}

    def stream_writer(self, payload: dict) -> None:
        self.events.append(payload)


def _init_db(monkeypatch, tmp_path: Path, workspace: Path) -> str:
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "diag.db"))

    from app import db

    db.init_db()
    project_row = db.create_project("诊断测试", str(workspace))
    return db.create_session("诊断会话", project_row["id"])["id"]


def _drive_command_tool(session_id: str, workspace: Path, command: str) -> str:
    from app.agent.core.context import AgentRunContext
    from app.agent.tools.execution import _handle_adapter_call
    from app.tools.registry import get_tool

    ctx = AgentRunContext(
        session_id=session_id,
        workspace=workspace,
        # full：跳过终端确认，测试里没人应答审批。
        approval_mode="full",
        plan_choice_resolved=True,
    )
    runtime = _StubRuntime()
    adapter = get_tool("terminal")
    assert adapter is not None
    return asyncio.run(
        _handle_adapter_call(ctx, runtime, adapter, "terminal", {"command": command})
    )


def test_execution_appends_diagnosis_on_command_failure(
    monkeypatch, tmp_path: Path
):
    workspace = tmp_path / "ws"
    (workspace / "app").mkdir(parents=True)
    (workspace / "app" / "__init__.py").write_text("", encoding="utf-8")
    (workspace / "app" / "store.py").write_text(_STORE_PY, encoding="utf-8")
    (workspace / "boom.py").write_text(
        "from app import store\n\n\ndef main():\n    return store.get_by_id('x')\n"
        "\n\nmain()\n",
        encoding="utf-8",
    )
    session_id = _init_db(monkeypatch, tmp_path, workspace)

    content = _drive_command_tool(
        session_id, workspace, f"{sys.executable} boom.py"
    )
    assert "[诊断]" in content
    assert "KeyError" in content
    assert "app/store.py" in content
    assert "fingerprint:" in content


def test_execution_skips_diagnosis_on_success(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "ok.py").write_text("print('all good')\n", encoding="utf-8")
    session_id = _init_db(monkeypatch, tmp_path, workspace)

    content = _drive_command_tool(session_id, workspace, f"{sys.executable} ok.py")
    assert "[诊断]" not in content
