"""站点配方（recipe，031 §7）：URL 模式匹配注入流程知识，替代"适配器"。

配方文件放在 `<data_root>/browser/recipes/*.json`，形态：

```json
{
  "name": "meituan-waimai",
  "version": 3,
  "url_patterns": ["*waimai.meituan.com*"],
  "flow_hints": "结算在「确认订单」二级页…",
  "quirks": ["首进有全屏弹窗先关"]
}
```

- 命中 URL → flow_hints/quirks 作为提示片段注入 browser 子 agent（不改工具集）；
- 不命中 → 纯通用循环；配方失效 = 退化为通用循环（变慢变贵，功能不失效）；
- 配方由人工审核入库（页面内容可能含注入，自动沉淀的草稿必须过人审）。
"""

from __future__ import annotations

import json
import logging
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

logger = logging.getLogger("divine.browser.recipes")


def recipes_dir() -> Path:
    from ...config import data_root

    return data_root() / "browser" / "recipes"


def load_recipes() -> list[dict[str, Any]]:
    """读取全部配方文件；坏文件跳过并告警。"""
    recipes: list[dict[str, Any]] = []
    directory = recipes_dir()
    if not directory.is_dir():
        return recipes
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not payload.get("url_patterns"):
                continue
            payload["_file"] = path.name
            recipes.append(payload)
        except Exception as exc:  # noqa: BLE001 — 单个坏文件不拖垮整体
            logger.warning("配方文件解析失败 %s: %s", path.name, exc)
    return recipes


def match_recipes(url: str) -> list[dict[str, Any]]:
    """返回 URL 命中的配方（可能多个，按文件名序）。"""
    lowered = (url or "").lower()
    if not lowered:
        return []
    hits: list[dict[str, Any]] = []
    for recipe in load_recipes():
        for pattern in recipe.get("url_patterns") or []:
            if fnmatch(lowered, str(pattern).lower()):
                hits.append(recipe)
                break
    return hits


def recipe_block(url: str) -> str | None:
    """命中的配方渲染为注入子 agent 系统提示的片段；无命中返回 None。"""
    hits = match_recipes(url)
    if not hits:
        return None
    blocks: list[str] = ["本任务目标站点存在以下已审核配方，优先按配方流程操作："]
    for recipe in hits:
        name = str(recipe.get("name") or recipe.get("_file") or "recipe")
        version = recipe.get("version") or 1
        blocks.append(f"[配方 {name} v{version}]")
        hints = str(recipe.get("flow_hints") or "").strip()
        if hints:
            blocks.append(hints)
        for quirk in recipe.get("quirks") or []:
            blocks.append(f"- 注意: {quirk}")
    return "\n".join(blocks)
