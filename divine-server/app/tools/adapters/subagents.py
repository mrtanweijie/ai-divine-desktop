from __future__ import annotations

from typing import Any

from ..base import ToolAdapter, ToolExecutionError
from ..registry import register_tool


@register_tool(
    "run_subagents",
    "把一个大任务拆成多个相互独立的子任务，并行委托给多个子 Agent 执行。"
    "适用于同时调研多个主题/产品/来源、并行分析多份资料、多角度对比等场景。"
    "每个子任务必须提供 id、name 和自包含的 prompt（子 Agent 看不到本对话历史，"
    "prompt 要写清背景、目标、数据来源和输出要求）；"
    "默认子 Agent 只能使用只读工具。若多个子任务需要并行写文件（如同时实现多个独立模块/文件），"
    "给对应子任务加 write=true 并声明 write_paths（workspace 内相对路径，可指向文件或目录，"
    "各子任务的 write_paths 不得重叠）；写任务的改动会汇总成 diff 返回，且执行前需用户确认。"
    "不要委托需要运行命令或交互确认的子任务；"
    "全部完成后把每个子任务的结果汇总成最终回答，失败的子任务要说明原因。",
    {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": (
                    "子任务数组，2-8 个；每个含 id、name、prompt，可选 tools 白名单、write、write_paths"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "子任务唯一 id（如 sa-1）",
                        },
                        "name": {
                            "type": "string",
                            "description": "面板显示的短标题（如“调研定价”）",
                        },
                        "prompt": {
                            "type": "string",
                            "description": (
                                "自包含的任务说明：写清背景、目标、数据来源和输出要求，"
                                "给出明确可执行的动作（如“用 web_fetch 访问 X，提取 Y”）；"
                                "写任务要说明每个文件写什么内容"
                            ),
                        },
                        "tools": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选工具白名单，默认只读工具集",
                        },
                        "write": {
                            "type": "boolean",
                            "description": (
                                "true 时该子任务可写文件（write_file/edit_files），"
                                "必须同时提供 write_paths；默认 false 只读"
                            ),
                            "default": False,
                        },
                        "write_paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "写任务允许创建/修改的 workspace 内相对路径（文件或目录），"
                                "各写任务之间不得重叠"
                            ),
                        },
                    },
                    "required": ["id", "name", "prompt"],
                },
            },
            "max_parallel": {
                "type": "integer",
                "description": "可选，最大并行数，默认 3，上限 4",
            },
        },
        "required": ["tasks"],
    },
)
class RunSubagentsAdapter(ToolAdapter):
    """Meta tool schema placeholder.

    Execution never reaches this adapter: ``execution.py`` special-cases the
    ``run_subagents`` tool name and dispatches to
    ``agent.subagents._run_subagents``. The ``run`` method exists only so the
    registry holds a valid adapter for schema listing and raises when someone
    bypasses the agent path.
    """

    timeout = 300

    async def run(
        self,
        workspace: Any,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any = None,
    ) -> Any:
        raise ToolExecutionError("run_subagents 是内部元工具，不可直接执行")
