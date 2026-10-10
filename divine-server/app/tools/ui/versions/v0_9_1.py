"""中立 IR → A2UI v0.9.1 消息。

规范基线见 ``docs/design/028-a2ui-integration-20261009.md`` §1.2。

消息形状（每帧自带 ``version``）::

    {"version":"v0.9.1","createSurface":{"surfaceId":..,"catalogId":..}}
    {"version":"v0.9.1","updateComponents":{"surfaceId":..,"components":[..]}}
    {"version":"v0.9.1","updateDataModel":{"surfaceId":..,"path":"/","value":{..}}}

**与 A2UI 基础目录（basic catalog）的一处有意偏差**：基础目录的 ``Button``
用 ``child`` 指向一个 ``Text`` 组件当标签，我们把 ``text`` 直接放在
``Button`` 上。这是**自定义目录（custom catalog）的正规用法**——A2UI 的
``catalogId`` 机制就是为「客户端声明自己的组件契约」而存在的，
``divine_catalog.json`` 里 ``Button.props`` 明确声明了 ``text``。
好处是 IR ↔ 目录 ↔ 前端镜像三处完全同构，不需要为「一个按钮」合成
一个隐藏的 Text 组件（那会让前端的回放与 diff 都多一层间接）。

``action`` 则严格按 v0.9.1 的 **envelope** 形态输出
（``{"event": {"name": ..., "context": [...]}}``），因为它是协议层结构，
不是目录内的组件契约。
"""

from __future__ import annotations

from typing import Any

from ..catalog import A2UI_VERSION, CATALOG_ID

#: 组件的哪些键属于结构（其余都是组件属性，原样透传）。
_STRUCTURAL_KEYS = ("id", "component", "children", "child", "action")


def _convert_component(raw: dict[str, Any]) -> dict[str, Any]:
    """把一个中立 IR 组件翻译成 v0.9.1 组件对象。

    除了 ``action`` 需要换成 envelope 形态外，其余字段一一对应
    （邻接表模型本就与 v0.9.1 一致：扁平数组 + ``id`` 互引）。
    """
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "action" and isinstance(value, dict):
            event: dict[str, Any] = {"name": value.get("name")}
            context = value.get("context")
            if isinstance(context, list) and context:
                event["context"] = context
            out["action"] = {"event": event}
            continue
        out[key] = value
    return out


def to_messages(surface: dict[str, Any]) -> list[dict[str, Any]]:
    """把**已校验并归一化**的 surface 转成一帧 A2UI v0.9.1 消息。

    调用方保证 ``surface`` 来自 ``validator.validate_ui_surface`` 的
    ``normalized``（已裁剪、已保证 root 存在）。
    """
    surface_id = str(surface.get("surfaceId") or "")
    components = [_convert_component(c) for c in surface.get("components") or []]

    messages: list[dict[str, Any]] = [
        {
            "version": A2UI_VERSION,
            "createSurface": {
                "surfaceId": surface_id,
                "catalogId": CATALOG_ID,
            },
        },
        {
            "version": A2UI_VERSION,
            "updateComponents": {
                "surfaceId": surface_id,
                "components": components,
            },
        },
    ]
    data = surface.get("data")
    if isinstance(data, dict) and data:
        messages.append(
            {
                "version": A2UI_VERSION,
                "updateDataModel": {
                    "surfaceId": surface_id,
                    "path": "/",
                    "value": data,
                },
            }
        )
    return messages


def to_sse_payload(
    surface: dict[str, Any],
    *,
    seq: int = 1,
    source_call_id: str | None = None,
) -> dict[str, Any]:
    """构造 ``event: a2ui`` 的载荷（交给 ``agent/core/sse.py`` 透传）。

    **帧内完整性铁律**（044 §5.1）：一帧里的 ``messages`` 必须完整，
    不做 JSONL 跨帧拼接。代价是首帧延迟，收益是解析零歧义。

    ``title`` 放**帧封装顶层**（与 ``surfaceId``/``seq`` 同级），不塞进
    ``createSurface``：后者是 A2UI 协议消息，往里加自定义字段会污染协议
    形状（将来换版本/对齐官方实现时是要还的债）。帧封装本就是我们自己的
    结构，``surfaceId`` 已经这么用了。
    """
    surface_id = str(surface.get("surfaceId") or "")
    payload: dict[str, Any] = {
        "event": "a2ui",
        "surfaceId": surface_id,
        "seq": seq,
        "messages": to_messages(surface),
    }
    title = surface.get("title")
    if isinstance(title, str) and title.strip():
        payload["title"] = title.strip()
    if source_call_id:
        payload["source_call_id"] = source_call_id
    return payload
