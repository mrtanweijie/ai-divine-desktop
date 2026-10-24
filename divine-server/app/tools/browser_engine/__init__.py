"""通用 Web 任务执行引擎（031）：L0 浏览器操作层。

包结构：
- session:  CDP 会话管理（专用 profile / 端口发现 / 专属 tab / 连接缓存）
- snapshot: aria 快照 + ref 映射（规模上限 / ref 过期）
- engine:   9 个操作实现（风险闸门 / 节奏 / 截图 caption 扩展点）
- risk:     风险四级判定（intent 标注 + 高风险词典 + 凭据禁令）
- policy:   域策略包钩子（购物包：金额护栏 / 免密警示）
"""

from .risk import classify_action, credential_hit, normalize_intent, refusal_payload
from .session import BrowserSession, launch_debug_chrome, manager
from .snapshot import build_snapshot

__all__ = [
    "BrowserSession",
    "build_snapshot",
    "classify_action",
    "credential_hit",
    "launch_debug_chrome",
    "manager",
    "normalize_intent",
    "refusal_payload",
]
