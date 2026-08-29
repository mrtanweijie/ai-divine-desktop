"""简单翻译本地分流：_is_simple_translation 判定。

中英互译（词/短语/短句）1.5B 实测合格 → 本地直答省 token；
小语种（日/韩/法…）会编造 → 不分流；长文本/非翻译 → 不分流。
"""

from __future__ import annotations


def _is(text: str) -> bool:
    from app.api.chat import _is_simple_translation

    return _is_simple_translation(text)


def test_simple_en_translation_local():
    assert _is('"简单" 英文怎么翻译') is True
    assert _is("你好 用英语怎么说") is True
    assert _is("请把这句话翻译成英文：This is great") is True
    assert _is("translate hello into chinese") is True


def test_bare_translation_marker():
    """裸'翻译' + 短内容 → 本地（'吃什么 翻译'）。"""
    assert _is("吃什么 翻译") is True
    assert _is("翻译：苹果") is True
    assert _is("苹果 翻译") is True


def test_document_translation_not_local():
    """文档/长文翻译 → 云端。"""
    assert _is("翻译这个文件") is False
    assert _is("帮我翻译这个文件") is False
    assert _is("请把这份文档翻译成英文") is False
    assert _is("把全文翻译成英文") is False
    assert _is("翻译这份文档") is False


def test_small_language_not_local():
    """小语种 1.5B 会编造，不分流。"""
    assert _is("苹果 用日语怎么说") is False
    assert _is("你好 用韩语怎么说") is False
    assert _is("你好 用法语怎么说") is False


def test_non_translation_not_local():
    assert _is("今天天气怎么样") is False
    assert _is("帮我打开计算器") is False
    assert _is("帮我整理这段文字") is False


def test_long_translation_not_local():
    long_text = "请把下面这段翻译成英文：" + "内容" * 300
    assert _is(long_text) is False
