"""消息文本里的 file:// URL 自动提取为附件。

背景：用户从地址栏/文本粘贴的 file:// 链接（含 percent 编码）原样发给
模型会触发工具调用异常（空工具名 / is not a valid tool）；发送时提取为
附件后，agent 通过 approved_paths 可直接 read_file。
"""

from __future__ import annotations


def _extract(text: str, tmp_path, filename: str = "测试 文件.html"):
    from urllib.parse import quote

    from app.api.chat import _extract_file_url_attachments

    f = tmp_path / filename
    f.write_text("<html>test</html>", encoding="utf-8")
    # 真实 file:// URL 的空格是 percent 编码（%20），浏览器/文件管理器如此
    url = "file://" + quote(str(f), safe="/")
    return _extract_file_url_attachments(f"{text}{url}")


def test_extract_url_with_context(tmp_path):
    """消息里带 file:// URL + 其他文本 → URL 转附件，文本保留。"""
    cleaned, attachments = _extract("帮我读一下 ", tmp_path)
    assert cleaned == "帮我读一下"
    assert len(attachments) == 1
    assert attachments[0].name == "测试 文件.html"
    assert attachments[0].file_path == str(tmp_path / "测试 文件.html")
    assert attachments[0].size is not None


def test_extract_pure_url_message(tmp_path):
    """整条消息只有 file:// URL → 全部转附件，文本清空（走"请分析附件"）。"""
    cleaned, attachments = _extract("", tmp_path)
    assert cleaned == ""
    assert len(attachments) == 1


def test_extract_percent_encoded(tmp_path):
    """percent 编码的 URL 解码后正确提取。"""
    from urllib.parse import quote

    from app.api.chat import _extract_file_url_attachments

    f = tmp_path / "风控模块提测测试要点思维导图.html"
    f.write_text("<html>x</html>", encoding="utf-8")
    url = "file://" + quote(str(f))
    cleaned, attachments = _extract_file_url_attachments(url)
    assert cleaned == ""
    assert len(attachments) == 1
    assert attachments[0].file_path == str(f)


def test_extract_keeps_missing_file_url(tmp_path):
    """文件不存在的 URL 保留原文（让模型告知用户路径不存在）。"""
    from app.api.chat import _extract_file_url_attachments

    cleaned, attachments = _extract_file_url_attachments(
        "file:///nonexistent/xxx.html"
    )
    assert attachments == []
    assert cleaned == "file:///nonexistent/xxx.html"


def test_extract_no_url_unchanged(tmp_path):
    from app.api.chat import _extract_file_url_attachments

    cleaned, attachments = _extract_file_url_attachments("帮我整理这段文字")
    assert cleaned == "帮我整理这段文字"
    assert attachments == []
