"""browser 工具集（031 §4，9 个）——L0 浏览器操作的 LLM 接口。

设计约束：
- **不进主 agent 工具表**（category="browser"，tools.py 按类别跳过），仅由
  browser 子 agent 注册（subagents.py 的 browser 任务分支）；主 agent 只拿
  ``web_task`` 一个委派入口；
- 变更操作（click/fill/select/scroll）执行后自动带新快照，同一来回完成；
- ``intent`` 为风险标注（read/reversible/irreversible），引擎层用高风险词典
  兜底判定，irreversible 动作仅在 confirmed=true 委派段放行；
- ``_sid`` 由子 agent 运行器注入（聊天会话 1:1 浏览器会话），直连调用时
  退化为按 workspace 隔离。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolResult
from ..registry import register_tool
from ..browser_engine import engine
from ..browser_engine.session import manager

_CATEGORY = "browser"

_INTENT_PARAM = {
    "type": "string",
    "enum": ["read", "reversible", "irreversible"],
    "description": (
        "风险标注：read=只读，reversible=可逆变更，irreversible=不可逆变更。"
        "元素名称命中高风险词典（提交/支付/删除/发送等）时系统会无视标注"
        "一律按不可逆处理，因此不要试图用标注绕过确认"
    ),
}


def _session_key(arguments: dict[str, Any], workspace: Path) -> str:
    """子 agent 注入的聊天会话键；缺失时按 workspace 隔离（直连调用兜底）。"""
    sid = str(arguments.pop("_sid", "") or "").strip()
    return sid or f"ws:{workspace.resolve()}"


def _result(payload: dict[str, Any]) -> ToolResult:
    return ToolResult(
        success=bool(payload.get("success")),
        message=str(payload.get("message") or ("执行完成" if payload.get("success") else "执行失败")),
        content=json.dumps(payload, ensure_ascii=False),
    )


class _BrowserAdapter(ToolAdapter):
    category = _CATEGORY
    allow_external_paths = True

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any = None,
    ) -> ToolResult:
        key = _session_key(arguments, workspace)
        session = manager.get(key)
        payload = await self._operate(session, workspace, arguments)
        if payload.get("fatal"):
            manager.drop(key)
        return _result(payload)

    async def _operate(
        self, session: Any, workspace: Path, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        raise NotImplementedError


@register_tool(
    "browser_navigate",
    "在会话专属标签页打开 URL（仅 http/https），返回新页面 aria 快照（结构化文本+元素 ref）",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要打开的页面地址（http/https）"}
        },
        "required": ["url"],
    },
)
class BrowserNavigateAdapter(_BrowserAdapter):
    timeout = 60

    async def _operate(self, session, workspace, arguments):
        return await engine.op_navigate(session, workspace, str(arguments.get("url") or ""))


@register_tool(
    "browser_snapshot",
    "获取当前页面 aria 快照（结构化文本+元素 ref）；传 ref 可只取该元素子树（大页面优先用）",
    {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "可选：只快照该元素子树"}
        },
    },
)
class BrowserSnapshotAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        return await engine.op_snapshot(session, workspace, arguments.get("ref"))


@register_tool(
    "browser_click",
    "点击元素并返回新快照。优先按快照 ref；无 role 的纯文本节点（H5 门店卡片等拿不到 ref）"
    "用 text 按可见文本点击（支持部分匹配）。不可逆动作（提交/支付/删除等）仅在 "
    "confirmed=true 委派段放行",
    {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "快照里的元素 ref，例如 e12（与 text 二选一）"},
            "text": {
                "type": "string",
                "description": "元素可见文本（可只给部分），用于快照里无 ref 的纯文本节点（与 ref 二选一）",
            },
            "intent": _INTENT_PARAM,
        },
    },
)
class BrowserClickAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        return await engine.op_click(
            session,
            workspace,
            arguments.get("ref"),
            arguments.get("text"),
            arguments.get("intent"),
        )


@register_tool(
    "browser_fill",
    "按快照 ref 向输入框填入文本，返回新快照；密码/验证码/API key 类字段无条件拒绝",
    {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "输入框元素 ref"},
            "text": {"type": "string", "description": "要填入的文本"},
            "intent": _INTENT_PARAM,
        },
        "required": ["ref", "text"],
    },
)
class BrowserFillAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        return await engine.op_fill(
            session,
            workspace,
            str(arguments.get("ref") or ""),
            str(arguments.get("text") or ""),
            arguments.get("intent"),
        )


@register_tool(
    "browser_select",
    "按快照 ref 选择下拉选项（先按可见文本、后按 value 匹配），返回新快照",
    {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "下拉框元素 ref"},
            "option": {"type": "string", "description": "选项可见文本或 value"},
        },
        "required": ["ref", "option"],
    },
)
class BrowserSelectAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        return await engine.op_select(
            session,
            workspace,
            str(arguments.get("ref") or ""),
            str(arguments.get("option") or ""),
        )


@register_tool(
    "browser_scroll",
    "滚动页面（down/up），返回新快照；默认 600 像素",
    {
        "type": "object",
        "properties": {
            "direction": {"type": "string", "enum": ["down", "up"]},
            "amount": {"type": "integer", "description": "滚动像素，默认 600"},
        },
        "required": ["direction"],
    },
)
class BrowserScrollAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        return await engine.op_scroll(
            session, workspace, str(arguments.get("direction") or "down"), arguments.get("amount")
        )


@register_tool(
    "browser_extract",
    "结构化抽取：按 ref 取元素文本/链接，或按 CSS 选择器组批量取字段（价格/商品卡/表单值等）；"
    "命中购物域名时自动附带金额护栏与免密警示",
    {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "可选：单元素抽取"},
            "selectors": {
                "type": "object",
                "description": '可选：字段名→CSS 选择器映射，如 {"prices": ".price"}',
                "additionalProperties": {"type": "string"},
            },
        },
    },
)
class BrowserExtractAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        selectors = arguments.get("selectors")
        return await engine.op_extract(
            session, workspace, arguments.get("ref"), selectors if isinstance(selectors, dict) else None
        )


@register_tool(
    "browser_wait",
    "等待条件出现（元素选择器/文本/URL 片段），返回最新快照",
    {
        "type": "object",
        "properties": {
            "condition": {
                "type": "object",
                "description": '三选一：{"selector": ".x"} / {"text": "发货中"} / {"url_contains": "paid"}',
            },
            "timeout": {"type": "integer", "description": "超时秒数，默认 15，上限 60"},
        },
        "required": ["condition"],
    },
)
class BrowserWaitAdapter(_BrowserAdapter):
    timeout = 90

    async def _operate(self, session, workspace, arguments):
        condition = arguments.get("condition")
        return await engine.op_wait(
            session, workspace, condition if isinstance(condition, dict) else {}, arguments.get("timeout")
        )


@register_tool(
    "browser_press_key",
    "向焦点元素发送键盘按键（Enter/Tab/Escape/ArrowDown/Control+A 等，可先按 ref 聚焦），返回新快照。"
    "用于回车提交、关闭浮层、键盘遍历；回车/Tab 可能触发表单提交，提交类按键只应在 confirmed=true 委派段使用",
    {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "按键表达式，如 Enter、Tab、Escape、ArrowDown、Control+A"},
            "ref": {"type": "string", "description": "可选：先聚焦该元素再按键"},
        },
        "required": ["key"],
    },
)
class BrowserPressKeyAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        return await engine.op_press_key(
            session, workspace, str(arguments.get("key") or ""), arguments.get("ref")
        )


@register_tool(
    "browser_read_page",
    "元素截图（存入工作区 browser/ 子目录，仅作视觉描述的一次性输入，用完即删）→ "
    "返回 caption 或降级可见文本摘要。快照里读得到的内容不要用本工具",
    {"type": "object", "properties": {}},
)
class BrowserReadPageAdapter(_BrowserAdapter):
    timeout = 60

    async def _operate(self, session, workspace, arguments):
        return await engine.op_read_page(session, workspace)
