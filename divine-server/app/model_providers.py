"""模型提供商目录：默认内置 + 用户可编辑的 JSON 配置文件。

配置文件位于 ``{data_root}/divine-model-provider.json``（与 settings.json 同目录），
用户可手动编辑，也可让 Agent 通过 manage_model_providers 工具更新。
文件缺失时自动写入内置默认副本；文件存在则整体覆盖内置目录（以文件为准）。
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from .config import data_root

logger = logging.getLogger("divine.model_providers")

# 提供商列表（按顺序显示）——内置默认；divine-model-provider.json 存在时以文件为准
DEFAULT_MODEL_PROVIDERS: list[dict[str, Any]] = [
    {
        "value": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-flash",
        "list": ["deepseek-flash", "deepseek-v4-pro"],
        "prefix": ["deepseek"],
    },
    {
        "value": "xiaomi",
        "label": "Xiaomi (MiMo)",
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "default_model": "mimo-v2.5",
        "list": ["mimo-v2.5", "mimo-v2.5-pro"],
        "prefix": ["mimo"],
    },
    {
        "value": "glm",
        "label": "GLM (智谱)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-5.3-flash",
        "list": [
            "glm-5.3",
            "glm-5.3-flash",
            "glm-5.2",
            "glm-5",
            "glm-5v-turbo",
            "glm-image",
            "glm-4.7-flash",
            "glm-4.6v-flash",
        ],
        "prefix": ["glm"],
    },
    {
        "value": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-5.5",
        "list": ["gpt-5.6", "gpt-5.5", "gpt-5.4", "gpt-4.1", "gpt-4.1-mini", "gpt-4o"],
        "prefix": ["gpt"],
    },
    {
        "value": "minimax",
        "label": "MiniMax",
        "base_url": "https://api.minimaxi.com/v1",
        "default_model": "MiniMax-M3",
        "list": ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.5", "MiniMax-M2.1"],
        "prefix": ["minimax"],
    },
    {
        "value": "qwen",
        "label": "Qwen (通义千问)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen3.8-max",
        "list": [
            "qwen3.8-max",
            "qwen3.7-max",
            "qwen3.7-plus",
            "qwen3.7-flash",
            "qwen3.6-plus",
            "qwen-vl-max",
        ],
        "prefix": ["qwen"],
    },
    {
        "value": "tencent",
        "label": "Tencent",
        "base_url": "https://tokenhub.tencentmaas.com/v1",
        "default_model": "hy4-preview",
        "list": ["hy4-preview"],
        "prefix": ["hy"],
    },
    {
        "value": "local",
        "label": "本地模型 (llama.cpp)",
        "base_url": "http://127.0.0.1:8016/v1",
        "default_model": "local",
        "list": [],
        "prefix": ["local"],
    },
    {
        "value": "custom",
        "label": "自定义",
        "base_url": "",
        "default_model": "",
        "list": [],
        "prefix": [],
    },
]


def providers_config_path() -> Path:
    return data_root() / "divine-model-provider.json"


def _normalize_entry(entry: Any) -> dict[str, Any] | None:
    """宽松校验单个提供商条目：value 必填，其余字段归一为安全类型。"""
    if not isinstance(entry, dict):
        return None
    value = str(entry.get("value") or "").strip()
    if not value:
        return None

    def _str_list(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [item.strip() for item in raw if isinstance(item, str) and item.strip()]

    return {
        "value": value,
        "label": str(entry.get("label") or value),
        "base_url": str(entry.get("base_url") or ""),
        "default_model": str(entry.get("default_model") or ""),
        "list": _str_list(entry.get("list")),
        "prefix": _str_list(entry.get("prefix")),
    }


def load_model_providers(create_missing: bool = True) -> tuple[list[dict[str, Any]], Path]:
    """读取生效的提供商目录，返回 (providers, 配置文件路径)。

    文件缺失时写入内置默认副本（方便用户直接改），文件存在时整体覆盖默认。
    解析失败的条目跳过并记日志，不让一个坏条目拖垮整个目录。
    """
    path = providers_config_path()
    if not path.exists():
        if create_missing:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(DEFAULT_MODEL_PROVIDERS, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                logger.warning("无法写入提供商配置文件 %s，使用内置默认", path)
        return [dict(entry) for entry in DEFAULT_MODEL_PROVIDERS], path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("提供商配置文件 %s 解析失败，使用内置默认", path)
        return [dict(entry) for entry in DEFAULT_MODEL_PROVIDERS], path
    entries = raw.get("providers") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        logger.warning("提供商配置文件 %s 结构不符（应为数组），使用内置默认", path)
        return [dict(entry) for entry in DEFAULT_MODEL_PROVIDERS], path
    providers = [
        normalized
        for entry in entries
        if (normalized := _normalize_entry(entry)) is not None
    ]
    if not providers:
        logger.warning("提供商配置文件 %s 无有效条目，使用内置默认", path)
        return [dict(entry) for entry in DEFAULT_MODEL_PROVIDERS], path
    return providers, path


def save_model_providers(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """校验并原子写入提供商目录，返回规范化后的条目。"""
    path = providers_config_path()
    normalized = [
        normalized
        for entry in (entries or [])
        if (normalized := _normalize_entry(entry)) is not None
    ]
    if not normalized:
        raise ValueError("提供商列表不能为空")
    values = [entry["value"] for entry in normalized]
    if len(values) != len(set(values)):
        raise ValueError("提供商 value 重复")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")
        Path(tmp).replace(path)
    finally:
        tmp_path = Path(tmp)
        if tmp_path.exists():
            tmp_path.unlink()
    logger.info("提供商目录已更新 %s（%d 个提供商）", path, len(normalized))
    return normalized


def upsert_model_provider(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """按 value 增改单个提供商，保留原有顺序（新增追加到 custom 之前）。"""
    normalized = _normalize_entry(entry)
    if not normalized:
        raise ValueError("提供商条目缺少必填的 value")
    providers, _ = load_model_providers(create_missing=False)
    for index, existing in enumerate(providers):
        if existing["value"] == normalized["value"]:
            providers[index] = normalized
            break
    else:
        insert_at = next(
            (
                index
                for index, existing in enumerate(providers)
                if existing["value"] == "custom"
            ),
            len(providers),
        )
        providers.insert(insert_at, normalized)
    return save_model_providers(providers)


def remove_model_provider(value: str) -> list[dict[str, Any]]:
    """按 value 删除提供商；custom 与 local 为系统保留，不可删除。"""
    value = str(value or "").strip()
    if value in ("custom", "local"):
        raise ValueError(f"{value} 为系统保留提供商，不可删除")
    providers, _ = load_model_providers(create_missing=False)
    remaining = [entry for entry in providers if entry["value"] != value]
    if len(remaining) == len(providers):
        raise ValueError(f"没有找到提供商 {value}")
    return save_model_providers(remaining)
