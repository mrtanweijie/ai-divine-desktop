"""browser_engine 风险分级与购物策略钩子的离线单测（031 §6.1/§14.3）。"""

from __future__ import annotations

import pytest

from app.tools.browser_engine import policy, risk


# ---------------------------------------------------------------------------
# risk.classify_action — 词典兜底优先于 intent 标注
# ---------------------------------------------------------------------------


def test_lexicon_overrides_intent():
    # 命中词典 → 无视标注一律 irreversible（防 agent 误标绕过）
    level, hit = risk.classify_action("提交订单", "read")
    assert level == "irreversible"
    assert hit == "提交订单"


def test_lexicon_partial_match():
    level, _ = risk.classify_action("一键删除全部草稿", None)
    assert level == "irreversible"


def test_irreversible_intent_honored_without_lexicon():
    level, hit = risk.classify_action("确认收货地址", "irreversible")
    assert level == "irreversible"
    assert hit is None


def test_default_is_reversible():
    level, hit = risk.classify_action("收藏商品", None)
    assert level == "reversible"
    assert hit is None


def test_read_intent():
    level, _ = risk.classify_action("查看商品详情", "read")
    assert level == "read"


def test_english_terms():
    level, hit = risk.classify_action("Place Order", None)
    assert level == "irreversible"
    assert hit == "place order"


def test_empty_name_defaults_reversible():
    level, _ = risk.classify_action("", None)
    assert level == "reversible"


# ---------------------------------------------------------------------------
# risk.normalize_intent — 非法标注返回 None
# ---------------------------------------------------------------------------


def test_normalize_intent_valid():
    assert risk.normalize_intent("IRREVERSIBLE") == "irreversible"
    assert risk.normalize_intent(None) is None


def test_normalize_intent_invalid():
    assert risk.normalize_intent("bypass") is None
    assert risk.normalize_intent(123) is None


# ---------------------------------------------------------------------------
# risk.credential_hit — 凭据输入禁令
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,expected",
    [
        ("请输入支付密码", "密码"),
        ("短信验证码", "验证码"),
        ("Password", "password"),
        ("API Key", "api key"),
        ("收货地址", None),
        ("搜索商品", None),
    ],
)
def test_credential_hit(field, expected):
    assert risk.credential_hit(field) == expected


def test_refusal_payload_shape():
    payload = risk.refusal_payload("拒绝", risk="irreversible", target="提交订单")
    assert payload["success"] is False
    assert payload["rejected"] is True
    assert payload["risk"] == "irreversible"


# ---------------------------------------------------------------------------
# policy.evaluate_shopping_policy — 域名命中 / 免密警示 / 金额护栏
# ---------------------------------------------------------------------------


@pytest.fixture()
def default_settings(monkeypatch):
    monkeypatch.setattr(policy, "_load_settings", lambda: {})


def test_non_shopping_domain_returns_none(default_settings):
    assert policy.evaluate_shopping_policy("https://example.com/page", "应付 ¥100") is None


def test_shopping_domain_matched(default_settings):
    result = policy.evaluate_shopping_policy("https://h5.waimai.meituan.com/order", "应付 ¥16.5")
    assert result is not None
    assert result["domain_pack"] == "shopping"
    assert result["amount_guard"]["verdict"] == "pass"


def test_amount_exceeds_cap_blocks(default_settings):
    result = policy.evaluate_shopping_policy("https://item.jd.com/1.html", "应付 ¥258.00")
    guard = result["amount_guard"]
    assert guard["amount"] == 258.0
    assert guard["per_order_cap"] == 200.0
    assert guard["verdict"] == "block"
    assert any("超过单笔上限" in w for w in result["warnings"])


def test_mianmi_warning(default_settings):
    result = policy.evaluate_shopping_policy(
        "https://cart.taobao.com/checkout", "支付方式：小额免密支付 已开启；应付 ¥16.5"
    )
    assert any("免密" in w for w in result["warnings"])


def test_custom_cap_from_settings(monkeypatch):
    monkeypatch.setattr(policy, "_load_settings", lambda: {"shopping_per_order_cap": 300})
    result = policy.evaluate_shopping_policy("https://item.jd.com/1.html", "合计 ¥258")
    assert result["amount_guard"]["verdict"] == "pass"


def test_settled_amount_preferred_over_any_price(default_settings):
    # 页面有多个价格时，优先取"应付/合计"附近那个
    text = "单品价 ¥9.9 运费 ¥2 应付 ¥11.9"
    result = policy.evaluate_shopping_policy("https://item.taobao.com/x", text)
    assert result["amount_guard"]["amount"] == 11.9


def test_custom_domains_from_settings(monkeypatch):
    monkeypatch.setattr(
        policy, "_load_settings", lambda: {"shopping_policy_domains": "example.com"}
    )
    assert policy.match_domain_pack("https://example.com/buy") == "shopping"
    assert policy.match_domain_pack("https://jd.com/x") is None
