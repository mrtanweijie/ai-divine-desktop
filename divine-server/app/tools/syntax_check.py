"""编辑后轻量语法检查（P3-3a）。

agent 改完文件立即做零依赖的语法验证，错误文本回灌给模型自我修复，
而不是等用户运行时才发现。只做"快而准"的检查：
- Python → ``py_compile``（批量、单次子进程）；
- JSON → ``json.loads``；
- YAML → ``yaml.safe_load``（yaml 可用时）。
不做类型检查/lint（run_tests/lint_check 工具已覆盖）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_MAX_FILES = 20
_PY_TIMEOUT = 20
_MAX_PROBLEMS = 10
_MAX_PROBLEM_CHARS = 500

_PATCH_TARGET_RE = re.compile(r"^\+\+\+ (?:b/)?(.+)$", re.MULTILINE)


def edited_paths(
    name: str, arguments: dict[str, Any], workspace: Path | None = None
) -> list[str]:
    """Extract the file paths a successful edit tool touched.

    相对路径按 ``workspace`` 解析为绝对路径（服务进程 CWD 与工作区无关）。
    """
    paths: list[str] = []
    if name == "edit_files":
        for item in arguments.get("files") or []:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item["path"]))
    elif name in {"write_file", "edit_lines"}:
        if arguments.get("path"):
            paths.append(str(arguments["path"]))
    elif name == "apply_patch":
        patch = str(arguments.get("patch") or "")
        for match in _PATCH_TARGET_RE.finditer(patch):
            target = match.group(1).strip()
            if target and target != "/dev/null":
                paths.append(target)
    resolved: list[str] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute() and workspace is not None:
            path = workspace / path
        resolved.append(str(path))
    seen: set[str] = set()
    unique: list[str] = []
    for path in resolved:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique[:_MAX_FILES]


def _check_python(paths: list[Path]) -> list[str]:
    """Batch py_compile; stderr already contains per-file locations."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", *[str(p) for p in paths]],
            capture_output=True,
            text=True,
            timeout=_PY_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode == 0:
        return []
    detail = (proc.stderr or proc.stdout or "").strip()
    if not detail:
        detail = "; ".join(p.name for p in paths)
    return [f"Python 语法错误:\n{detail[-1000:]}"]


def _check_json(path: Path) -> str | None:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return None  # 非 UTF-8 文本，跳过
    except OSError:
        return None
    except json.JSONDecodeError as exc:
        return f"JSON 语法错误 {path.name}: {exc}"
    return None


def _check_yaml(path: Path) -> str | None:
    try:
        import yaml
    except ImportError:
        return None
    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return None
    except OSError:
        return None
    except Exception as exc:  # noqa: BLE001 — yaml 错误类型多，统一捕获
        return f"YAML 语法错误 {path.name}: {str(exc)[:300]}"
    return None


def syntax_check_paths(paths: list[str]) -> list[str]:
    """Check the given files; return human-readable problems (may be empty).

    不存在的文件、不可检查的类型直接跳过；单文件内容损坏/过大以跳过处理，
    语法检查绝不能让一次成功的编辑变成失败。
    """
    problems: list[str] = []
    py_files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".py":
            py_files.append(path)
        elif suffix == ".json":
            problem = _check_json(path)
            if problem:
                problems.append(problem)
        elif suffix in {".yaml", ".yml"}:
            problem = _check_yaml(path)
            if problem:
                problems.append(problem)
    if py_files:
        problems.extend(_check_python(py_files))
    problems = problems[:_MAX_PROBLEMS]
    return [p[:_MAX_PROBLEM_CHARS] for p in problems]
