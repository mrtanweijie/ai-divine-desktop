"""A2UI 协议版本边界。

业务侧（``validator`` / ``adapters/render_ui.py``）**只产出中立 IR**；
把 IR 翻译成具体协议版本的消息，全部发生在这一层。

升级到 v1.0（``actionResponse`` 客户端→服务端 RPC、``theme`` 更名
``surfaceProperties``）时，只改这里 + ``versions/v1_0.py``，业务代码零改动。

见 ``docs/design/028-a2ui-integration-20261009.md`` §12.1。
"""

from __future__ import annotations

from . import v0_9_1
from .v0_9_1 import to_messages, to_sse_payload

__all__ = ["v0_9_1", "to_messages", "to_sse_payload"]
