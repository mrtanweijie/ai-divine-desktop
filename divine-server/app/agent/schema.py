"""Tool argument schemas and skill script runners."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import ConfigDict, create_model

def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                value = part.get("text") or part.get("content")
                if value:
                    parts.append(str(value))
        return "".join(parts)
    return str(content) if content else ""

def _schema_annotation(schema: dict[str, Any]) -> Any:
    enum_values = schema.get("enum")
    if enum_values:
        values = [
            value
            for value in enum_values
            if isinstance(value, (str, int, float, bool))
        ]
        literals = tuple(Literal[value] for value in values)
        return literals[0] if len(literals) == 1 else Union[literals]

    schema_type = schema.get("type")
    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        return list[_schema_annotation(schema.get("items") or {})]
    if schema_type == "object":
        return dict[str, Any]
    for key in ("anyOf", "oneOf"):
        sub_schemas = schema.get(key)
        if sub_schemas:
            annotations = [_schema_annotation(item) for item in sub_schemas]
            return annotations[0] if len(annotations) == 1 else Union[tuple(annotations)]
    return Any

def _make_args_model(
    name: str, parameters: dict[str, Any] | None
) -> Any:
    parameters = parameters or {}
    properties = parameters.get("properties") or {}
    if not properties:
        return None
    required = set(parameters.get("required") or [])
    fields: dict[str, tuple[Any, Any]] = {}
    for prop_name, prop_schema in properties.items():
        annotation = _schema_annotation(prop_schema or {})
        if prop_name in required:
            fields[prop_name] = (annotation, ...)
        else:
            fields[prop_name] = (Optional[annotation], None)
    return create_model(
        f"{name}_args",
        __config__=ConfigDict(extra="allow"),
        **fields,
    )

def _skill_tool_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_-")
    return f"skill_{cleaned or 'script'}"

def _skill_script_timeout() -> int:
    try:
        return max(1, int(os.getenv("DIVINE_SKILL_SCRIPT_TIMEOUT", "120")))
    except ValueError:
        return 120

def _run_skill_script(
    script: Path,
    skill_dir: Path,
    mode: str,
    params: dict[str, Any] | None,
    args: list[str] | None,
    timeout: int | None,
) -> Any:
    timeout = timeout or _skill_script_timeout()
    command = [sys.executable, str(script)]
    stdin_text: str | None = None
    if mode == "json":
        stdin_text = json.dumps({"params": params or {}}, ensure_ascii=False)
    else:
        command.extend(str(item) for item in (args or []))

    try:
        completed = subprocess.run(
            command,
            input=stdin_text,
            capture_output=True,
            text=True,
            cwd=str(skill_dir),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"技能脚本执行超时（{timeout}s）") from exc
    except OSError as exc:
        raise RuntimeError(f"无法启动技能脚本: {exc}") from exc

    stdout_text = completed.stdout or ""
    stderr_text = completed.stderr or ""
    if completed.returncode != 0:
        detail = stderr_text.strip() or stdout_text.strip()
        raise RuntimeError(
            "技能脚本退出码 %d：%s"
            % (completed.returncode, detail[-500:] if detail else "无输出")
        )

    if mode == "json":
        try:
            return json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            tail = stderr_text.strip()[-200:] if stderr_text.strip() else ""
            raise RuntimeError(
                "技能脚本未返回合法 JSON: "
                + stdout_text[-300:]
                + (f"；stderr: {tail}" if tail else "")
            ) from exc

    output = stdout_text.strip()
    if stderr_text.strip():
        output = output + ("\n" if output else "") + "[stderr]\n" + stderr_text.strip()[-2000:]
    if not output:
        output = "（技能脚本无输出）"
    if len(output) > 30000:
        output = output[:30000] + "\n...[输出已截断]"
    return output

def _skill_args_model(name: str, mode: str) -> Any:
    model_name = f"{_skill_tool_name(name)}_args".replace("-", "_")
    if mode == "json":
        return create_model(
            model_name,
            params=(dict[str, Any], ...),
            timeout=(Optional[int], None),
        )
    return create_model(
        model_name,
        args=(Optional[list[str]], None),
        timeout=(Optional[int], None),
    )
