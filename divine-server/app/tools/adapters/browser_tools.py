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
    "点击元素并返回新快照。三种定位（按优先级）：ref（快照元素）→ text（可见文本，"
    "用于无 role 的纯文本卡片）→ selectors（CSS 定位，用于图片绘制的无障碍盲区按钮，"
    "如美团「+」加购图标）。不可逆动作（提交/支付/删除等）仅在 confirmed=true 委派段放行",
    {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "快照里的元素 ref，例如 e12"},
            "text": {
                "type": "string",
                "description": "元素可见文本（可只给部分），用于快照里无 ref 的纯文本节点",
            },
            "selectors": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": 'CSS 定位兜底，如 {".cart-add": ".cart-add"}；取第一个 key 的选择器',
            },
            "intent": _INTENT_PARAM,
        },
    },
)
class BrowserClickAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        selectors = arguments.get("selectors")
        return await engine.op_click(
            session,
            workspace,
            arguments.get("ref"),
            arguments.get("text"),
            arguments.get("intent"),
            selectors if isinstance(selectors, dict) else None,
        )


@register_tool(
    "browser_read_captcha",
    "图形验证码识别：按 ref 截取验证码元素 → 视觉模型识别 → 返回验证码字符"
    "（用 browser_fill 填入验证码输入框）。识别失败返回 code=null，降级为登录卡片人工认读，"
    "不要反复重试。仅 confirmed=true 委派段可填入验证码",
    {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "验证码图片元素的 ref"},
        },
        "required": ["ref"],
    },
)
class BrowserReadCaptchaAdapter(_BrowserAdapter):
    timeout = 60

    async def _operate(self, session, workspace, arguments):
        return await engine.op_read_captcha(
            session, workspace, str(arguments.get("ref") or "")
        )


@register_tool(
    "browser_solve_slider",
    "滑块验证码自动求解（实验性，仅 confirmed=true 委派段）：按手柄/滑轨 ref 截图"
    "→ Pillow 像素分析定位缺口 → 拟人轨迹拖拽（分段缓动+过冲+抖动）→ 可选成功标记检测。"
    "失败最多重试 1 次后必须降级有头人工拖拽（行为风控下成功率不稳定，避免风险分累积）",
    {
        "type": "object",
        "properties": {
            "handle_ref": {"type": "string", "description": "滑块手柄元素 ref"},
            "track_ref": {"type": "string", "description": "滑轨/验证码容器元素 ref（截图分析对象）"},
            "piece_ref": {"type": "string", "description": "可选：缺口拼图元素 ref（双图差分更准）"},
            "success_text": {"type": "string", "description": "可选：成功标记文本（如「验证成功」），用于拖拽后检测"},
        },
        "required": ["handle_ref", "track_ref"],
    },
)
class BrowserSolveSliderAdapter(_BrowserAdapter):
    timeout = 60

    async def _operate(self, session, workspace, arguments):
        return await engine.op_solve_slider(
            session,
            workspace,
            str(arguments.get("handle_ref") or ""),
            str(arguments.get("track_ref") or ""),
            arguments.get("piece_ref"),
            arguments.get("success_text"),
        )


@register_tool(
    "browser_solve_click_captcha",
    "点选验证码自动求解（实验性，仅 confirmed=true 委派段）：验证码容器截图 → "
    "视觉模型读出目标并定位坐标（targets 缺省时自动读提示与目标）→ 按顺序模拟点击 "
    "→ 可选确认按钮与成功标记检测。geetest 类 canvas 无障碍盲区用 selector 定位。"
    "识别失败返回 points=null，降级为有头人工点选，不要盲目点击",
    {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS 定位验证码容器（geetest 常见 .geetest_widget 内 canvas/img）",
            },
            "image_ref": {"type": "string", "description": "或：验证码大图元素 ref（与 selector 二选一）"},
            "targets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选：按点击顺序给定的目标文本；缺省时由视觉模型读图中提示",
            },
            "submit_text": {"type": "string", "description": "可选：选完后的确认按钮文本（如「确认」）"},
            "success_text": {"type": "string", "description": "可选：成功标记文本（如「验证成功」），用于检测"},
        },
    },
)
class BrowserSolveClickCaptchaAdapter(_BrowserAdapter):
    timeout = 60

    async def _operate(self, session, workspace, arguments):
        targets = arguments.get("targets")
        return await engine.op_solve_click_captcha(
            session,
            workspace,
            arguments.get("image_ref"),
            arguments.get("selector"),
            targets if isinstance(targets, list) else None,
            arguments.get("submit_text"),
            arguments.get("success_text"),
        )


@register_tool(
    "browser_capture",
    "元素截图并持久化到工作区（返回绝对路径，含现成 markdown 字段可粘贴到正文"
    "渲染进对话流）。ref/selector 定位元素；都不传则截当前 viewport 兜底"
    "（二维码等孤立元素优先用定位）。典型用途：扫码登录二维码展示，"
    "配合 browser_wait 等登录成功标记",
    {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "快照元素 ref（如二维码 img/canvas）"},
            "selector": {"type": "string", "description": "或 CSS 选择器定位元素"},
            "name": {"type": "string", "description": "文件名前缀（如 qr），默认 capture"},
        },
    },
)
class BrowserCaptureAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        return await engine.op_capture(
            session,
            workspace,
            arguments.get("ref"),
            arguments.get("selector"),
            str(arguments.get("name") or "capture"),
        )


@register_tool(
    "browser_sniff_start",
    "开始嗅探匹配正则的网络请求（API 模拟登录第 1 步）：随后在页面上执行操作"
    "（如 UI 登录），引擎记录匹配的 XHR/fetch，完成后 browser_sniff_stop 取回"
    "请求模板（method/url/status/post_data）",
    {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "URL 匹配正则，如 login|signin|auth|captcha",
            },
        },
        "required": ["pattern"],
    },
)
class BrowserSniffStartAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        return await engine.op_sniff_start(
            session, workspace, str(arguments.get("pattern") or "")
        )


@register_tool(
    "browser_sniff_stop",
    "停止嗅探并返回捕获的请求模板。判断：POST + 明文手机号/密码/验证码字段 + 2xx "
    "→ 可 API 重放；body 含加密密码/动态签名 → 放弃，回退 UI 登录",
    {"type": "object", "properties": {}},
)
class BrowserSniffStopAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        return await engine.op_sniff_stop(session, workspace)


@register_tool(
    "browser_api_login",
    "API 模拟登录（仅 confirmed=true 委派段）：重放嗅探到的登录请求（httpx），"
    "把响应 Set-Cookie 注入浏览器上下文——不开 UI、不碰验证码的会话恢复。"
    "目标域必须与当前任务页面同域；body 由 ask_user 收到的凭据填入模板构造",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "嗅探到的登录接口 URL"},
            "method": {"type": "string", "description": "HTTP 方法，默认 POST"},
            "body": {"type": "string", "description": "请求体（JSON 文本，凭据已填入）"},
            "headers": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "可选：额外请求头",
            },
        },
        "required": ["url"],
    },
)
class BrowserApiLoginAdapter(_BrowserAdapter):
    timeout = 60

    async def _operate(self, session, workspace, arguments):
        headers = arguments.get("headers")
        return await engine.op_api_login(
            session,
            workspace,
            str(arguments.get("url") or ""),
            str(arguments.get("method") or "POST"),
            arguments.get("body"),
            headers if isinstance(headers, dict) else None,
        )


@register_tool(
    "browser_api_call",
    "站点 API 通用调用（登录/注册/数据接口统一通道，与 UI 平行）：GET 只读数据"
    "自动附浏览器登录态 cookie、无需确认；非 GET 或带 body（登录/注册/变更）需 "
    "confirmed=true，inject_cookies=true 把响应 cookie 注入浏览器。目标域必须与"
    "当前任务页面同域。接口模板来自 browser_sniff_start/stop 嗅探",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "同站 API 地址（嗅探所得）"},
            "method": {"type": "string", "description": "HTTP 方法，默认 GET"},
            "body": {"type": "string", "description": "请求体（JSON 文本）；带 body 需 confirmed"},
            "headers": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "可选：额外请求头",
            },
            "send_cookies": {
                "type": "boolean",
                "description": "是否附浏览器当前 cookie（默认 true，登录态数据接口必需）",
            },
            "inject_cookies": {
                "type": "boolean",
                "description": "是否把响应 Set-Cookie 注入浏览器（登录场景，默认 false）",
            },
        },
        "required": ["url"],
    },
)
class BrowserApiCallAdapter(_BrowserAdapter):
    timeout = 60

    async def _operate(self, session, workspace, arguments):
        headers = arguments.get("headers")
        return await engine.op_api_call(
            session,
            workspace,
            str(arguments.get("url") or ""),
            str(arguments.get("method") or "GET"),
            arguments.get("body"),
            headers if isinstance(headers, dict) else None,
            arguments.get("send_cookies", True) is not False,
            bool(arguments.get("inject_cookies")),
        )


@register_tool(
    "browser_geometry",
    "读取元素的几何信息（x/y/width/height + devicePixelRatio），支持 CSS 选择器或快照 ref。"
    "用于布局判断、验证码浮层定位等——替代 JS evaluate 取 rect",
    {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS 选择器（如 .geetest_widget canvas）"},
            "ref": {"type": "string", "description": "快照元素 ref"},
        },
    },
)
class BrowserGeometryAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        return await engine.op_geometry(
            session,
            workspace,
            arguments.get("selector"),
            arguments.get("ref"),
        )


@register_tool(
    "browser_track_order",
    "提交订单后启动订单状态后台轮询：定期重新加载当前页检查标记文本（如「支付成功」），"
    "命中/超时经事件流通知用户。轮询不占用委派段生命周期——启动后即可结束汇报",
    {
        "type": "object",
        "properties": {
            "marker": {
                "type": "string",
                "description": "订单成功状态的标记文本，如「支付成功」「订单已提交」",
            },
            "timeout_minutes": {"type": "integer", "description": "最长追踪分钟数，默认 15，上限 60"},
            "interval_seconds": {"type": "integer", "description": "轮询间隔秒数，默认 60，范围 10-300"},
        },
        "required": ["marker"],
    },
)
class BrowserTrackOrderAdapter(_BrowserAdapter):
    timeout = 30

    async def _operate(self, session, workspace, arguments):
        return await engine.op_track_order(
            session,
            workspace,
            arguments.get("marker"),
            arguments.get("timeout_minutes"),
            arguments.get("interval_seconds"),
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
