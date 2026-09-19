"""故障诊断层：把异常栈文本解析成结构化的定位信息。

与 ``command_output.py`` 的分工：后者做「CLI 汇总 → 计数」，本模块做
「异常 → 栈帧」。两者职责不同，混在一起会让现有 7 个解析器的测试变脆
（design 026 §8）。

定位机制是**结构化栈帧解析**，不引入 embedding / 向量库（项目原则）——
栈帧本身就是精确的 ``file:line``，语义检索在这里是多余的。

解析失败绝不能把一次成功的工具调用变成失败：所有解析器对畸形输入
一律返回空列表，不抛异常（沿用 ``syntax_check`` 的既有约定）。
"""

from __future__ import annotations

import hashlib
import os
import re
import sysconfig
from dataclasses import dataclass, field
from pathlib import Path

# ---- 输出预算（design 026 §2.5）------------------------------------------------
_MAX_TRACEBACKS = 10
_MAX_FRAMES = 8
_MAX_CODE_CHARS = 200
_MAX_MESSAGE_CHARS = 300
_MAX_BLOCK_CHARS = 2000

# ---- 非业务路径判定（design 026 §2.4）------------------------------------------
# 依赖目录 / 虚拟环境 / 元数据目录：这些栈帧对根因判断有用，但不是"该去改的代码"。
_DEP_DIR_MARKERS = (
    "/site-packages/",
    "/dist-packages/",
    "/node_modules/",
    "/dist-info/",
    "/.venv/",
    "/venv/",
    "/.tox/",
    "/.git/",
)
# 伪文件：解释器生成的代码，没有可读源码。
_PSEUDO_FILE_PREFIXES = (
    "<frozen",
    "<string>",
    "<stdin>",
    "<attrs generated",
    "<ipython-input",
    "<template>",
    "<unknown>",
)
# 伪路径：``node:internal/process/task_queues``、``webpack:///./src/a.ts`` 这类
# 不是文件系统路径，不能按 workspace 归属去判——否则会被当成工作区内的相对路径。
# 负向前瞻排除 Windows 盘符（``C:/...`` 归一后仍带冒号）。
_SCHEME_PATH_RE = re.compile(r"^[a-zA-Z][\w+.-]*:(?!/)")
# 测试文件：属于工作区代码，但"业务帧"（指纹锚点）要跳过它们——
# 否则同一个 bug 被两个测试打到会得到两个指纹，去重就失效了。
_TEST_PATH_RE = re.compile(
    r"(?:^|/)(?:tests?|__tests__|spec)/"
    r"|(?:^|/)test_[^/]*$"
    r"|_test\.[a-z]+$"
    r"|\.(?:test|spec)\.[a-z]+$"
)

# ---- 解析用正则 ----------------------------------------------------------------
# Python 完整 traceback：``  File "path", line 10, in func``
# 前缀允许 ``|`` / ``+`` 装饰，以兼容 ExceptionGroup 的 ``  |   File ...`` 画法。
_PY_FRAME_RE = re.compile(
    r"^[\s|+]*File \"(?P<file>[^\"]+)\", line (?P<line>\d+)(?:, in (?P<func>.*?))?\s*$",
    re.M,
)
# py_compile 的报错不带 ``, in func``，单独一条。
_PY_COMPILE_FRAME_RE = re.compile(
    r"^\s*File \"(?P<file>[^\"]+)\", line (?P<line>\d+)\s*$", re.M
)

# pytest 的帧行有三种写法，都要认（run_tests 用 tb=short，terminal 手跑默认 tb=long）：
#   tb=short 与 tb=long 中间帧：``tests/test_api.py:5: in test_login``
#   tb=long 首帧：            ``tests/test_api.py:5: ``（源码已单独打印在上一行）
#   tb=long 末帧：            ``app/db.py:5: KeyError``（尾部是异常名，没有 func）
_PYTEST_FRAME_RE = re.compile(
    r"^(?P<file>[^\s:][^:\n]*?):(?P<line>\d+):(?:[ \t]+(?P<tail>\S.*?))?[ \t]*$",
    re.M,
)
# pytest 失败段落头：``___________________ test_login ___________________``
_PYTEST_SECTION_RE = re.compile(
    r"^_{10,}[ \t]+(?P<name>.+?)[ \t]+_{10,}\s*$", re.M
)
# pytest 异常行：``E   KeyError: 'abc'``
_PYTEST_E_LINE_RE = re.compile(r"^E[ \t]{2,}(?P<rest>.+?)\s*$", re.M)

# Node：``at fn (/app/src/user.ts:10:15)`` / ``at /app/src/user.ts:10:15``
_NODE_FRAME_RE = re.compile(
    r"^\s*at\s+(?:(?P<func>[^()\n]+?)\s+\()?"
    r"(?P<file>[^()\s]+?):(?P<line>\d+):(?P<col>\d+)\)?\s*$",
    re.M,
)
# vitest 的 ``❯ tests/foo.test.ts:12:5``
_VITE_FRAME_RE = re.compile(
    r"^\s*[❯>]\s*(?P<file>[^\s:]+?):(?P<line>\d+):(?P<col>\d+)\s*$", re.M
)
# Node 顶层异常行：``TypeError: Cannot read properties of undefined``
_NODE_EXC_RE = re.compile(
    r"^(?P<exc>[A-Za-z_][\w.]*(?:Error|Exception))(?::\s*(?P<msg>.*))?$", re.M
)
# tsc / eslint：``src/a.ts(10,5): error TS2345: ...``
_TS_ERROR_RE = re.compile(
    r"^(?P<file>[^(\n]+?)\((?P<line>\d+),\d+\):\s+"
    r"(?:error|warning)\s+(?P<code>\S+):\s*(?P<msg>.*)$",
    re.M,
)

# ``ExceptionType: message``（异常名后可选消息）
_EXC_LINE_RE = re.compile(r"^(?P<exc>[A-Za-z_][\w.]*)(?::\s*(?P<msg>.*))?$")
# 这些行长得像异常但其实不是。
_NOISE_PREFIXES = (
    "Traceback (most recent call last)",
    "Traceback:",
    "During handling of the above exception",
    "The above exception was the direct cause",
    "Exception Group Traceback",
    "+ Exception Group Traceback",
    "Stack trace:",
)


@dataclass
class Frame:
    """一层调用栈帧。``file`` 在 workspace 内时是相对路径，越界时保留绝对路径。"""

    file: str
    line: int
    func: str
    code: str = ""
    is_user_code: bool = False
    is_business: bool = False


@dataclass
class FailureReport:
    """一次故障的结构化定位结果。"""

    kind: str  # "python_traceback" | "node_stack" | "compile" | "unknown"
    exception: str
    message: str
    frames: list[Frame] = field(default_factory=list)
    fingerprint: str = ""
    # pytest 失败段落头里的用例名（``___ test_login ___`` → ``test_login``）。
    # 用于把报告回挂到 run_tests 的 data.failures[]（按用例名匹配，比按序更稳）。
    node: str = ""

    def anchor(self) -> Frame | None:
        """指纹锚点帧：首个业务帧（跳过测试文件）。"""
        for frame in self.frames:
            if frame.is_business:
                return frame
        return None


# ---- 路径与源码工具 ------------------------------------------------------------


def _norm(path: str) -> str:
    """Windows 反斜杠归一为 ``/``（design 026 §9）。"""
    return path.replace("\\", "/")


def _stdlib_roots() -> tuple[str, ...]:
    roots: list[str] = []
    for key in ("stdlib", "platstdlib"):
        value = sysconfig.get_paths().get(key)
        if value:
            roots.append(_norm(os.path.realpath(value)))
    return tuple(roots)


_STDLIB_ROOTS = _stdlib_roots()


def _is_test_path(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(_norm(path)))


def _is_dependency_path(abs_path: str) -> bool:
    """绝对路径是否落在依赖/虚拟环境/标准库里。"""
    if any(marker in f"/{abs_path}" for marker in _DEP_DIR_MARKERS):
        return True
    return any(
        abs_path == root or abs_path.startswith(root + "/") for root in _STDLIB_ROOTS
    )


def _classify(path: str, workspace: Path | None) -> tuple[str, bool, bool]:
    """返回 ``(显示用路径, is_user_code, is_business)``。

    - 伪文件（``<frozen ...>``）与伪路径（``node:internal/...``）既无源码也非用户代码；
    - 越界路径（不在 workspace 内）不是用户代码，但保留绝对路径供判断根因；
    - workspace 内的依赖/标准库也不是用户代码；
    - 用户代码里的测试文件算 user_code，但不算 business（见 ``_TEST_PATH_RE``）。
    """
    raw = _norm(path)
    if raw.startswith(_PSEUDO_FILE_PREFIXES) or _SCHEME_PATH_RE.match(raw):
        return raw, False, False

    candidate_path = Path(raw)
    if not candidate_path.is_absolute() and workspace is not None:
        # 相对路径必须按 workspace 解析——服务进程的 CWD 与工作区无关
        # （同 syntax_check.edited_paths 的约定），否则整条工作区判定都会失效。
        candidate_path = Path(workspace) / raw
    candidate = os.path.realpath(candidate_path)
    abs_path = _norm(candidate)

    if workspace is not None:
        try:
            rel = os.path.relpath(candidate, os.path.realpath(workspace))
        except ValueError:  # 跨盘符（Windows）
            rel = None
        if rel is not None and not rel.startswith(".."):
            display = _norm(rel)
            if _is_dependency_path(abs_path):
                return display, False, False
            return display, True, not _is_test_path(display)

    # workspace 外：依赖/标准库不是用户代码；其余真实文件也不是（无法确认归属），
    # 但保留绝对路径——依赖内部逻辑对根因判断仍有用（design 026 §9）。
    return raw, False, False


class _SourceReader:
    """按需读取栈帧对应源码行，按文件缓存，避免同一文件反复 IO。"""

    def __init__(self, workspace: Path | None) -> None:
        self.workspace = workspace
        self._cache: dict[str, list[str]] = {}

    def line(self, display_path: str, lineno: int) -> str:
        if not display_path or display_path.startswith("<") or lineno <= 0:
            return ""
        candidates: list[Path] = []
        raw = Path(display_path)
        if raw.is_absolute():
            candidates.append(raw)
        elif self.workspace is not None:
            candidates.append(Path(self.workspace) / display_path)
        for path in candidates:
            key = str(path)
            if key not in self._cache:
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except (OSError, ValueError):
                    self._cache[key] = []
                else:
                    self._cache[key] = text.splitlines()
            lines = self._cache[key]
            if 0 < lineno <= len(lines):
                return lines[lineno - 1].strip()[:_MAX_CODE_CHARS]
        return ""


def _make_frame(
    reader: _SourceReader, raw_file: str, line: int, func: str, workspace: Path | None
) -> Frame:
    display, is_user, is_business = _classify(raw_file, workspace)
    return Frame(
        file=display,
        line=line,
        func=(func or "").strip()[:120],
        code=reader.line(display, line),
        is_user_code=is_user,
        is_business=is_business,
    )


def _cap_frames(frames: list[Frame]) -> list[Frame]:
    """最多 ``_MAX_FRAMES`` 帧，保持原始顺序（外侧 → 内侧）。

    保留原始顺序而非「业务帧提前」：最深帧才是异常抛出点，打乱顺序会丢掉
    「谁调用了谁」这条最重要的信息。名额不够时先丢外侧的非业务帧
    （依赖/标准库调用链对根因判断价值最低）。
    """
    if len(frames) <= _MAX_FRAMES:
        return frames
    business_idx = [i for i, f in enumerate(frames) if f.is_business]
    if len(business_idx) >= _MAX_FRAMES:
        chosen = set(business_idx[:_MAX_FRAMES])
    else:
        remaining = _MAX_FRAMES - len(business_idx)
        non_idx = [i for i, f in enumerate(frames) if not f.is_business]
        # 非业务帧从内侧取——离异常最近的那几层最可能相关。
        chosen = set(business_idx) | set(non_idx[-remaining:])
    return [f for i, f in enumerate(frames) if i in chosen]


def _looks_like_exception(name: str) -> bool:
    tail = name.rsplit(".", 1)[-1]
    if not tail[:1].isupper():
        return False
    return any(
        key in tail
        for key in (
            "Error",
            "Exception",
            "Warning",
            "Exit",
            "Interrupt",
            "Iteration",
            "Stop",
            "Fault",
            "Failure",
            "Timeout",
        )
    )


def _split_exception_line(text: str) -> tuple[str, str]:
    match = _EXC_LINE_RE.match(text.strip())
    if not match:
        return "", text.strip()[:_MAX_MESSAGE_CHARS]
    return match.group("exc"), (match.group("msg") or "").strip()[:_MAX_MESSAGE_CHARS]


def _pick_exception_line(lines: list[str], after: int) -> tuple[str, str]:
    """在 ``after`` 行之后挑异常行：先严格匹配异常名，退而求其次取最后一个候选。"""
    strict: tuple[str, str] | None = None
    relaxed: tuple[str, str] | None = None
    for raw in lines[after:]:
        text = re.sub(r"^[\s|+]+", "", raw).strip()
        if not text or text.startswith(_NOISE_PREFIXES):
            continue
        if _PY_FRAME_RE.match(raw) or _PY_COMPILE_FRAME_RE.match(raw):
            continue
        exc, msg = _split_exception_line(text)
        if not exc:
            continue
        relaxed = (exc, msg)
        if _looks_like_exception(exc):
            strict = (exc, msg)
    return strict or relaxed or ("", "")


def compute_fingerprint(exception: str, frames: list[Frame]) -> str:
    """``sha1(exception@首个业务帧 file:line)[:12]``（design 026 §2.3）。

    **不带 message**：消息里常有变量值（``KeyError: 'user_id'`` vs ``'uid'``），
    带上会让同一个 bug 的指纹漂移，去重就失效了。
    """
    anchor = None
    for frame in frames:
        if frame.is_business:
            anchor = frame
            break
    if anchor is None:
        for frame in frames:
            if frame.is_user_code:
                anchor = frame
                break
    key = (
        f"{exception}@{anchor.file}:{anchor.line}"
        if anchor is not None
        else f"{exception}@<no_user_frame>"
    )
    return hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:12]


# ---- 解析器 --------------------------------------------------------------------


def parse_python_traceback(
    text: str, workspace: Path | None = None
) -> list[FailureReport]:
    """完整 traceback 块 → 报告；支持多 traceback / 嵌套异常 / ExceptionGroup。"""
    if "Traceback (most recent call last)" not in text:
        return []
    reader = _SourceReader(workspace)
    reports: list[FailureReport] = []
    for block in text.split("Traceback (most recent call last):")[1:]:
        lines = block.splitlines()
        frames: list[Frame] = []
        last_frame_line = -1
        for index, raw in enumerate(lines):
            match = _PY_FRAME_RE.match(raw)
            if not match:
                continue
            frames.append(
                _make_frame(
                    reader,
                    match.group("file"),
                    int(match.group("line")),
                    match.group("func") or "",
                    workspace,
                )
            )
            last_frame_line = index
        if not frames:
            continue
        exc, msg = _pick_exception_line(lines, last_frame_line + 1)
        if not exc:
            continue
        frames = _cap_frames(frames)
        reports.append(
            FailureReport(
                kind="python_traceback",
                exception=exc,
                message=msg,
                frames=frames,
                fingerprint=compute_fingerprint(exc, frames),
            )
        )
        if len(reports) >= _MAX_TRACEBACKS:
            break
    return reports


def parse_pytest_short(
    text: str, workspace: Path | None = None
) -> list[FailureReport]:
    """pytest ``--tb=short`` 段落 → 报告。

    ``run_tests`` 用的正是 ``--tb=short``，它的帧长这样：
    ``tests/test_api.py:5: in test_login``——**没有** ``Traceback (most recent
    call last):`` 头，所以完整 traceback 解析器抓不到，必须单独一条。
    """
    sections = list(_PYTEST_SECTION_RE.finditer(text))
    if not sections:
        return []
    reader = _SourceReader(workspace)
    reports: list[FailureReport] = []
    for order, section in enumerate(sections):
        end = (
            sections[order + 1].start() if order + 1 < len(sections) else len(text)
        )
        body = text[section.end() : end]
        frames: list[Frame] = []
        trailing: list[str] = []
        for match in _PYTEST_FRAME_RE.finditer(body):
            tail = (match.group("tail") or "").strip()
            if tail.startswith("in "):
                func = tail[3:].strip()
            else:
                func = ""
                if tail:
                    trailing.append(tail)
            frames.append(
                _make_frame(
                    reader,
                    match.group("file"),
                    int(match.group("line")),
                    func,
                    workspace,
                )
            )
        if not frames:
            continue
        exc, msg = "", ""
        for match in _PYTEST_E_LINE_RE.finditer(body):
            candidate_exc, candidate_msg = _split_exception_line(match.group("rest"))
            if _looks_like_exception(candidate_exc):
                exc, msg = candidate_exc, candidate_msg
                break
            if not msg:  # 裸 assert：pytest 一律归为 AssertionError
                exc, msg = "AssertionError", match.group("rest").strip()[
                    :_MAX_MESSAGE_CHARS
                ]
        if not exc:
            # 没有 ``E`` 行时退回末帧尾部那个异常名（tb=long 的 ``app/db.py:5: KeyError``）。
            for tail in reversed(trailing):
                if _looks_like_exception(tail):
                    exc = tail
                    break
        if not exc:
            exc = "AssertionError"
        frames = _cap_frames(frames)
        reports.append(
            FailureReport(
                kind="python_traceback",
                exception=exc,
                message=msg,
                frames=frames,
                fingerprint=compute_fingerprint(exc, frames),
                node=section.group("name").strip(),
            )
        )
        if len(reports) >= _MAX_TRACEBACKS:
            break
    return reports


def parse_node_stack(
    text: str, workspace: Path | None = None
) -> list[FailureReport]:
    """Node 栈（jest / vitest / ts-node）→ 报告。"""
    matches = list(_NODE_FRAME_RE.finditer(text)) + list(
        _VITE_FRAME_RE.finditer(text)
    )
    if not matches:
        return []
    exc_match = _NODE_EXC_RE.search(text)
    if exc_match is None:
        return []
    exc = exc_match.group("exc")
    msg = (exc_match.group("msg") or "").strip()[:_MAX_MESSAGE_CHARS]
    reader = _SourceReader(workspace)
    frames = [
        _make_frame(
            reader,
            match.group("file"),
            int(match.group("line")),
            (match.groupdict().get("func") or ""),
            workspace,
        )
        for match in matches
    ]
    frames = _cap_frames(frames)
    return [
        FailureReport(
            kind="node_stack",
            exception=exc,
            message=msg,
            frames=frames,
            fingerprint=compute_fingerprint(exc, frames),
        )
    ]


def parse_compile_errors(
    text: str, workspace: Path | None = None
) -> list[FailureReport]:
    """编译期错误（py_compile / tsc）→ 报告。"""
    reader = _SourceReader(workspace)
    reports: list[FailureReport] = []
    py_frames = [
        _make_frame(
            reader, m.group("file"), int(m.group("line")), "", workspace
        )
        for m in _PY_COMPILE_FRAME_RE.finditer(text)
    ]
    if py_frames:
        exc_match = re.search(r"^(?P<exc>[A-Za-z_][\w.]*Error):\s*(?P<msg>.*)$", text, re.M)
        if exc_match:
            exc = exc_match.group("exc")
            msg = exc_match.group("msg").strip()[:_MAX_MESSAGE_CHARS]
            frames = _cap_frames(py_frames)
            reports.append(
                FailureReport(
                    kind="compile",
                    exception=exc,
                    message=msg,
                    frames=frames,
                    fingerprint=compute_fingerprint(exc, frames),
                )
            )
    for match in _TS_ERROR_RE.finditer(text):
        code = match.group("code")
        frames = _cap_frames(
            [
                _make_frame(
                    reader,
                    match.group("file"),
                    int(match.group("line")),
                    "",
                    workspace,
                )
            ]
        )
        reports.append(
            FailureReport(
                kind="compile",
                exception=code,
                message=match.group("msg").strip()[:_MAX_MESSAGE_CHARS],
                frames=frames,
                fingerprint=compute_fingerprint(code, frames),
            )
        )
        if len(reports) >= _MAX_TRACEBACKS:
            break
    return reports


_PARSERS_BY_RUNNER = {
    "pytest": (parse_pytest_short, parse_python_traceback),
    "jest": (parse_node_stack,),
    "vitest": (parse_node_stack,),
    "npm_test": (parse_node_stack,),
    "ruff": (parse_compile_errors,),
    "mypy": (parse_compile_errors,),
    "tsc": (parse_compile_errors,),
    "eslint": (parse_compile_errors,),
}
_SNIFF_ORDER = (
    parse_python_traceback,
    parse_pytest_short,
    parse_node_stack,
    parse_compile_errors,
)


def parse_failures(
    text: str,
    workspace: Path | None = None,
    runner: str | None = None,
) -> list[FailureReport]:
    """统一入口：按 runner 分派；未知则逐个嗅探，取首个有结果的解析器。

    只用「首个有结果」而不是「全部合并」——多个解析器可能匹配到同一段文本
    （如 pytest 输出里既有 ``Traceback:`` 又有短帧），合并会产出重复报告。
    """
    if not text:
        return []
    candidates = _PARSERS_BY_RUNNER.get((runner or "").strip().lower())
    for parser in candidates or _SNIFF_ORDER:
        try:
            reports = parser(text, workspace)
        except Exception:  # noqa: BLE001 — 解析失败不影响工具结果
            continue
        if reports:
            return reports[:_MAX_TRACEBACKS]
    return []


# ---- 渲染 ---------------------------------------------------------------------


def _short_path(path: str, limit: int = 52) -> str:
    """超长路径显示时截断成 ``…/末两段``（design 026 §9）。"""
    if len(path) <= limit:
        return path
    parts = path.split("/")
    if len(parts) <= 2:
        return path
    return "…/" + "/".join(parts[-2:])


def _render_frame(frame: Frame, anchor: Frame | None) -> list[str]:
    location = f"{_short_path(frame.file)}:{frame.line}"
    # 空 func 是「pytest tb=long 只给了 file:line」，不是真的模块级——别写成
    # <module>，那会把 get_by_id 这种函数帧标错。
    name = frame.func or "-"
    marker = ""
    if anchor is not None and frame is anchor:
        marker = "   <- 业务代码" if frame.is_business else "   <- 测试代码"
    lines = [f"    {location:<28} {name}{marker}"]
    if frame.code:
        lines.append(f"        {frame.code}")
    return lines


def format_failure_block(
    reports: list[FailureReport], workspace: Path | None = None
) -> str:
    """把报告渲染成回灌给模型的 ``[诊断]`` 段（design 026 §3）。

    只渲染首个报告：模型需要的是"去哪一行"，不是把所有失败读一遍；
    其余失败的数量在首行点明，完整日志仍在 content 里。
    """
    if not reports:
        return ""
    total = len(reports)
    head = (
        "[诊断] 1 个失败，定位如下："
        if total == 1
        else f"[诊断] {total} 个失败，首个异常定位如下："
    )
    lines = [head]
    first = reports[0]
    detail = f"{first.exception}: {first.message}" if first.message else first.exception
    lines.append(f"  {detail[:_MAX_MESSAGE_CHARS]}")
    lines.append("  frames:")
    anchor = first.anchor()
    for frame in first.frames:
        lines.extend(_render_frame(frame, anchor))
    lines.append(f"  fingerprint: {first.fingerprint}")
    if anchor is not None:
        lines.append(
            f"  → 直接 read_file {anchor.file} 第 {anchor.line} 行附近，"
            "不要重新全仓 grep。"
        )
    else:
        lines.append(
            "  → 错误发生在依赖内部，考虑版本/用法问题；"
            "核对调用方传参是否符合该依赖的约定。"
        )
    block = "\n".join(lines)
    if len(block) > _MAX_BLOCK_CHARS:
        block = block[: _MAX_BLOCK_CHARS - 24].rstrip() + "\n  （已截断，完整日志见 content）"
    return block


def diagnose_tool_output(
    text: str, workspace: Path | None = None, runner: str | None = None
) -> str:
    """命令类工具失败时的一站式回灌：解析 → 渲染；无可定位信息返回空串。

    整段兜住异常——诊断是增益，绝不能让一次工具调用变成失败
    （沿用 ``syntax_check`` 的既有约定）。调用方只需判断返回值是否为空。
    """
    try:
        reports = parse_failures(text, workspace, runner)
    except Exception:  # noqa: BLE001 — 解析失败不影响工具结果
        return ""
    if not reports:
        return ""
    try:
        return format_failure_block(reports, workspace)
    except Exception:  # noqa: BLE001 — 渲染失败不影响工具结果
        return ""


def trace_payload(report: FailureReport) -> dict[str, object]:
    """报告 → ``data.failures[].trace`` 的 JSON 友好结构（design 026 §3 双通道）。"""
    return {
        "kind": report.kind,
        "exception": report.exception,
        "message": report.message,
        "fingerprint": report.fingerprint,
        "frames": [
            {
                "file": frame.file,
                "line": frame.line,
                "func": frame.func,
                "code": frame.code,
                "is_user_code": frame.is_user_code,
                "is_business": frame.is_business,
            }
            for frame in report.frames
        ],
    }


def attach_traces(
    failures: list[dict], reports: list[FailureReport]
) -> list[dict]:
    """给 ``run_tests`` 的 ``data.failures[]`` 逐项补 ``trace`` 字段。

    两轮匹配：先按用例名（``tests/test_api.py::test_login`` 的末段 ↔ 报告 ``node``），
    再让剩下的项按出现顺序认领剩余报告。**必须分两轮**——若边遍历边回退，
    靠前的项会按顺序把报告抢走，靠后的项即使能按名精确匹配也拿不到了。

    匹配不上的项原样保留：``trace`` 是增益字段，缺了不影响原有消费方。
    返回新列表，不就地修改入参。
    """
    if not failures or not reports:
        return failures
    by_node: dict[str, FailureReport] = {}
    for report in reports:
        if report.node:
            by_node.setdefault(report.node, report)

    assigned: dict[int, FailureReport] = {}
    claimed: set[int] = set()
    for index, item in enumerate(failures):
        if not isinstance(item, dict):
            continue
        test_id = str(item.get("test") or "")
        if not test_id:
            continue
        report = by_node.get(test_id.split("::")[-1])
        if report is not None and id(report) not in claimed:
            assigned[index] = report
            claimed.add(id(report))

    leftover = [r for r in reports if id(r) not in claimed]
    for index, item in enumerate(failures):
        if index in assigned or not isinstance(item, dict) or not leftover:
            continue
        report = leftover.pop(0)
        assigned[index] = report
        claimed.add(id(report))

    return [
        {**item, "trace": trace_payload(assigned[index])}
        if index in assigned
        else item
        for index, item in enumerate(failures)
    ]
