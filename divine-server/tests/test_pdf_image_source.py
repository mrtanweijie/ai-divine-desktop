"""旅行配图图片源测试：必应中国关键词搜索（离线桩）与降级链路。"""

import asyncio

import pytest

from app.docgen.pdf import cover_builder
from app.docgen.pdf.cover_builder import (
    _inline_placeholder_images,
    _keyword_to_image_url,
    _parse_bing_image_results,
    _search_image_url,
)


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    monkeypatch.setattr(cover_builder, "_BING_IMAGE_CACHE", {})


BING_PAGE = (
    '<div class="imgpt"><a m="&#123;&quot;murl&quot;:&quot;http://a.com/x.jpg&quot;,'
    '&quot;turl&quot;:&quot;http://t/1.jpg&quot;&#125;"></a></div>'
    '<div class="imgpt"><a m="&#123;&quot;murl&quot;:&quot;http://b.com/y.png&quot;&#125;"></a></div>'
    '<div class="imgpt"><a m="not json"></a></div>'
    '<div class="imgpt"><a m="&#123;&quot;murl&quot;:&quot;http://a.com/x.jpg&quot;&#125;"></a></div>'
)


def test_parse_bing_results_extracts_murls_in_order():
    urls = _parse_bing_image_results(BING_PAGE)
    assert urls == ["http://a.com/x.jpg", "http://b.com/y.png"]  # 去重、跳过坏 JSON


def test_search_caches_per_keyword(monkeypatch):
    calls = {"search": 0, "fetch": []}

    def fake_urlopen(request, timeout):
        calls["search"] += 1

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, n):
                return BING_PAGE.encode("utf-8")

            headers = {"Content-Type": "text/html"}

        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        cover_builder, "_fetch_image_data", lambda src: calls["fetch"].append(src) or (b"x", "image/jpeg")
    )

    first = _search_image_url("喀纳斯湖")
    second = _search_image_url("喀纳斯湖")
    assert first == "http://a.com/x.jpg"  # 第一个可下载候选入选
    assert second == first
    assert calls["search"] == 1  # 第二次命中缓存，不再搜索


def test_search_failure_is_cached_as_none(monkeypatch):
    def boom(request, timeout):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert _search_image_url("喀纳斯湖") is None
    assert _search_image_url("喀纳斯湖") is None
    assert cover_builder._BING_IMAGE_CACHE["喀纳斯湖"] is None


def test_keyword_url_prefers_search_falls_back_to_picsum(monkeypatch):
    monkeypatch.setattr(cover_builder, "_search_image_url", lambda kw: "http://real/x.jpg")
    assert _keyword_to_image_url("禾木村") == "http://real/x.jpg"

    monkeypatch.setattr(cover_builder, "_search_image_url", lambda kw: None)
    url = _keyword_to_image_url("禾木村")
    assert url.startswith("https://picsum.photos/seed/")

    # 本身是图片链接的关键词直接透传
    assert _keyword_to_image_url("https://cdn.example.com/p.jpg") == "https://cdn.example.com/p.jpg"


def test_inline_keyword_img_downloads_and_embeds(monkeypatch):
    monkeypatch.setattr(cover_builder, "_search_image_url", lambda kw: "http://real/x.jpg")
    monkeypatch.setattr(
        cover_builder, "_image_data_uri", lambda url: "data:image/jpeg;base64,AAA"
    )
    html = (
        '<div class="page"><div class="ph">'
        '<img src="keyword:喀纳斯湖"/><span class="ph-cap">喀纳斯湖 · 晨雾</span>'
        "</div></div>"
    )
    result = _inline_placeholder_images(html, auto_fill=True)
    assert 'src="data:image/jpeg;base64,AAA"' in result
    assert "keyword:" not in result


def test_inline_keyword_failure_removes_img_keeps_placeholder(monkeypatch):
    monkeypatch.setattr(cover_builder, "_search_image_url", lambda kw: "http://real/x.jpg")
    monkeypatch.setattr(cover_builder, "_image_data_uri", lambda url: None)
    html = (
        '<div class="page"><div class="ph">'
        '<img src="keyword:喀纳斯湖"/><span class="ph-cap">喀纳斯湖 · 晨雾</span>'
        "</div></div>"
    )
    result = _inline_placeholder_images(html, auto_fill=True)
    assert "<img" not in result  # img 移除，.ph 渐变占位保留
    assert "喀纳斯湖 · 晨雾" in result


def test_collect_image_keywords_from_both_sources():
    from app.docgen.pdf.cover_builder import _collect_image_keywords

    html = (
        '<div class="ph"><img src="keyword:五彩滩"/><span class="ph-cap">x</span></div>'
        '<div class="photo-placeholder"><span class="photo-note">Photo · 禾木村 · 晨雾</span></div>'
    )
    keywords = _collect_image_keywords(html)
    assert any("五彩滩" in k for k in keywords)
    assert any("禾木村" in k for k in keywords)
