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
    "若子任务写完代码需要跑测试/检查验证，给对应子任务加 terminal=true："
    "可用 run_tests / lint_check / format_code，terminal 仅限安全只读命令"
    "（python3 -m pytest、npx tsc --noEmit 等，需确认的命令会被直接拒绝），执行前需用户确认。"
    "全部完成后把每个子任务的结果汇总成最终回答，失败的子任务要说明原因。",
    {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": (
                    "子任务数组，2-8 个；每个含 id、name、prompt，"
                    "可选 tools 白名单、write、write_paths、terminal"
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
                        "terminal": {
                            "type": "boolean",
                            "description": (
                                "true 时该子任务可执行验证命令：run_tests/lint_check/format_code，"
                                "terminal 仅限安全只读命令；整批执行前需用户确认。默认 false"
                            ),
                            "default": False,
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


@register_tool(
    "web_task",
    "把一个需要操作真实浏览器的网页任务委托给 browser 子 Agent 执行（通用 Web 任务引擎，"
    "支持任意 URL：查询/整理/表单/购物等）。子 Agent 在用户浏览器的专属标签页里"
    "导航、读取、抽取、点击，逐步返回结果。多段委派模式：先以默认 confirmed=false "
    "做导航/读取/抽取（不可逆动作会被拒绝），拿到结构化信息后由你渲染操作确认卡"
    "（金额/地址/变更内容等关键字段只来自抽取结果），用户确认后再以 confirmed=true "
    "委派执行提交/删除等不可逆动作。prompt 要自包含：写清目标 URL、要做什么、"
    "要返回哪些结构化字段。",
    {
        "type": "object",
        "properties": {
            "subagent_type": {
                "type": "string",
                "enum": ["browser"],
                "description": "子 Agent 类型，目前仅支持 browser",
            },
            "prompt": {
                "type": "string",
                "description": (
                    "自包含任务说明：目标 URL、要完成的操作、需要返回的结构化字段；"
                    "子 Agent 看不到本对话历史"
                ),
            },
            "confirmed": {
                "type": "boolean",
                "description": (
                    "true 时允许不可逆动作（提交/删除/支付跳转等），"
                    "必须在操作确认卡获用户确认后才能置 true；默认 false"
                ),
                "default": False,
            },
        },
        "required": ["subagent_type", "prompt"],
    },
)
class TaskAdapter(ToolAdapter):
    """Meta tool schema placeholder.

    Execution never reaches this adapter: ``execution.py`` special-cases the
    ``web_task`` tool name and dispatches to ``agent.subagents._run_browser_task``.
    """

    timeout = 300

    async def run(
        self,
        workspace: Any,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any = None,
    ) -> Any:
        raise ToolExecutionError("web_task 是内部元工具，不可直接执行")
