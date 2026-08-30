"""通用文档配图：把 Markdown 里的远程图片下载内嵌，失败降级占位块。

三级策略（与 travel 手册一致）的前两级：
1. 真实图片 URL（http/https）→ 下载内嵌（6s 超时、2MB 上限）；
2. keyword:关键词 → 按关键词取稳定网络图（picsum seed，无需 API key）；
3. 失败/超限 → 渲染为渐变占位块（保留图片说明文字）。

本地路径图片不处理（WeasyPrint 经 base_url 直接加载）。
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any

from ..pdf_theme_manager import _image_data_uri, _keyword_to_image_url

# ![alt](src)：alt 允许嵌套一层方括号，src 不含右括号与空白
_MD_IMG_RE = re.compile(r"(!\[(?:[^\[\]]|\[[^\]]*\])*\]\()\s*([^)\s]+)\s*\)")
_REMOTE_PREFIXES = ("http://", "https://", "keyword:")

# 单次文档最多内嵌的远程图片数，超出部分保持原样（防止超长渲染）
_MAX_INLINE_IMAGES = 12


def placeholder_html(caption: str) -> str:
    """图片下载失败时的渐变占位块（样式见渲染器注入的 .img-fallback）。"""
    text = html_lib.escape((caption or "配图").strip() or "配图")
    return f'<div class="img-fallback">{text}</div>'


def inline_markdown_images(markdown: str) -> str:
    """把 markdown 中的远程图片内嵌为 data URI；失败降级占位块。

    - ![alt](https://...)：下载内嵌；
    - ![alt](keyword:关键词)：关键词 → 稳定图片 URL → 下载内嵌；
    - 下载失败或超过 _MAX_INLINE_IMAGES：URL 保留原样（交给渲染器兜底）、
      keyword: 降级为占位块；
    - 本地相对/绝对路径不处理。
    """
    if not markdown or "](" not in markdown:
        return markdown

    state: dict[str, Any] = {"inlined": 0}

    def _replace(match: re.Match[str]) -> str:
        full, prefix, src = match.group(0), match.group(1), match.group(2).strip()
        alt = full[2 : full.index("](")] if "](" in full else "配图"
        keyword = ""
        if src.startswith("keyword:"):
            keyword = src[len("keyword:") :].strip()
        elif not src.startswith(("http://", "https://")):
            return full  # 本地路径
        if state["inlined"] >= _MAX_INLINE_IMAGES:
            return placeholder_html(alt) if keyword else full
        url = _keyword_to_image_url(keyword) if keyword else src
        uri = _image_data_uri(url)
        if not uri:
            # 下载失败：统一降级为占位块，避免渲染器再次发起不可控的网络请求
            return placeholder_html(alt)
        state["inlined"] += 1
        return f"{prefix}{uri})"

    return _MD_IMG_RE.sub(_replace, markdown)
