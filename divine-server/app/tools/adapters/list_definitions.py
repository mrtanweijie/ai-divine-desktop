from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool

_MAX_DEFS = 300

# --- Python (ast, precise) ---------------------------------------------------


def _py_signature(node: ast.AST) -> str:
    args = getattr(node, "args", None)
    if args is None:
        return ""
    try:
        rendered = ast.unparse(args)
    except Exception:  # noqa: BLE001 — 大纲生成永不失败
        return ""
    return f"({rendered})" if rendered != "" else "()"


def _python_outline(text: str) -> list[dict[str, Any]] | None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    items: list[dict[str, Any]] = []

    def visit(node: ast.AST, depth: int) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if isinstance(node, ast.ClassDef) else "function"
                prefix = "async def" if isinstance(child, ast.AsyncFunctionDef) else "def"
                items.append(
                    {
                        "line": child.lineno,
                        "kind": kind,
                        "name": f"{prefix} {child.name}{_py_signature(child)}",
                        "depth": depth,
                    }
                )
                visit(child, depth + 1)
            elif isinstance(child, ast.ClassDef):
                bases = ""
                if child.bases:
                    try:
                        bases = "(" + ", ".join(ast.unparse(b) for b in child.bases) + ")"
                    except Exception:  # noqa: BLE001
                        bases = "(...)"
                items.append(
                    {
                        "line": child.lineno,
                        "kind": "class",
                        "name": f"class {child.name}{bases}",
                        "depth": depth,
                    }
                )
                visit(child, depth + 1)

    visit(tree, 0)
    items.sort(key=lambda item: item["line"])
    return items[:_MAX_DEFS]

    visit(tree, 0)
    items.sort(key=lambda item: item["line"])
    return items[:_MAX_DEFS]


# --- 其他语言：行级正则启发式 -------------------------------------------------

_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    ".ts": [
        ("class", re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)")),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+(\w+)")),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(")),
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)")),
        ("type", re.compile(r"^\s*(?:export\s+)?type\s+(\w+)\s*=")),
    ],
    ".tsx": None,  # 复用 .ts
    ".js": [
        ("class", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)")),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+(\w+)")),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(")),
    ],
    ".jsx": None,
    ".rs": [
        ("fn", re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+)?(?:async\s+)?fn\s+(\w+)")),
        ("struct", re.compile(r"^\s*(?:pub\s+)?struct\s+(\w+)")),
        ("enum", re.compile(r"^\s*(?:pub\s+)?enum\s+(\w+)")),
        ("trait", re.compile(r"^\s*(?:pub\s+)?trait\s+(\w+)")),
        ("impl", re.compile(r"^\s*impl(?:<[^>]*>)?\s+(.+?)\s*\{")),
    ],
    ".go": [
        ("func", re.compile(r"^func\s+(?:\([^)]+\)\s*)?(\w+)\s*\(")),
        ("type", re.compile(r"^type\s+(\w+)\s+(?:struct|interface)\b")),
    ],
    ".java": [
        ("class", re.compile(r"^\s*(?:public|private|protected)?\s*(?:final\s+|abstract\s+)*class\s+(\w+)")),
        ("interface", re.compile(r"^\s*(?:public\s+)?interface\s+(\w+)")),
        ("record", re.compile(r"^\s*(?:public\s+)?record\s+(\w+)\s*\(")),
    ],
}
_PATTERNS[".tsx"] = _PATTERNS[".ts"]
_PATTERNS[".jsx"] = _PATTERNS[".js"]
_PATTERNS[".mts"] = _PATTERNS[".ts"]
_PATTERNS[".cts"] = _PATTERNS[".ts"]

# Python 走 ast 解析，不在正则表里
_SUPPORTED_EXTS = set(_PATTERNS) | {".py"}


def _regex_outline(ext: str, text: str) -> list[dict[str, Any]]:
    patterns = _PATTERNS.get(ext)
    if not patterns:
        return []
    items: list[dict[str, Any]] = []
    for no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "*", "#")):
            continue
        for kind, pattern in patterns:
            match = pattern.match(line)
            if match:
                items.append(
                    {"line": no, "kind": kind, "name": match.group(1).strip(), "depth": 0}
                )
                break
        if len(items) >= _MAX_DEFS:
            break
    return items


def _outline_for(ext: str, text: str) -> list[dict[str, Any]]:
    if ext == ".py":
        result = _python_outline(text)
        if result is not None:
            return result
        # 语法错误的 Python 文件退回正则兜底
    return _regex_outline(ext, text)


@register_tool(
    "list_definitions",
    "列出单个代码文件的结构大纲（类/函数/方法/接口等定义及其起始行号），"
    "用于大文件快速定位后再 read_file 精读或 edit_lines 编辑；比 grep 更结构化。"
    "Python 用语法解析精确提取；ts/tsx/js/jsx/rs/go/java 用启发式匹配。",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "workspace 内代码文件的相对路径或绝对路径",
            },
        },
        "required": ["path"],
    },
)
class ListDefinitionsAdapter(ToolAdapter):
    category = "files"
    timeout = 20

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any = None,
    ) -> ToolResult:
        del locale, progress_callback
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise ToolExecutionError("path 不能为空")
        target = Path(raw_path)
        if not target.is_absolute():
            target = workspace / target
        target = target.resolve()
        if not target.is_file():
            raise ToolExecutionError(f"文件不存在: {target}")
        ext = target.suffix.lower()
        if ext not in _SUPPORTED_EXTS:
            raise ToolExecutionError(
                f"暂不支持的大纲语言: {ext}（支持 .py/.ts/.tsx/.js/.jsx/.rs/.go/.java）；"
                "可用 grep_files 按关键字定位"
            )

        def _do_work() -> ToolResult:
            text = target.read_text(encoding="utf-8", errors="replace")
            items = _outline_for(ext, text)
            lines = [
                f"{item['line']:>6}  {'  ' * item['depth']}{item['kind']}: {item['name']}"
                for item in items
            ]
            rel = (
                target.relative_to(workspace.resolve()).as_posix()
                if target.is_relative_to(workspace.resolve())
                else str(target)
            )
            message = (
                f"{rel}: {len(items)} 个定义" if items else f"{rel}: 未识别到定义"
            )
            return ToolResult(
                success=True,
                message=message,
                content="\n".join(lines) if lines else "(空)",
                data={
                    "path": rel,
                    "count": len(items),
                    "items": items[:100],
                },
            )

        return await asyncio.to_thread(_do_work)
