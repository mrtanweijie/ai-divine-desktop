"""浏览器操作引擎（L0）：adapter 与快照/会话之间的操作实现层。

每个操作返回 ``{success, message?, ...}`` dict，由 adapter 转成 JSON content。
风险闸门在本层强制执行（031 §6.1）：
- irreversible 动作（词典命中或 intent 标注）仅在会话 ``confirmed=True``
  （web_task(confirmed=True) 委派段）时放行；
- 凭据类输入无条件拒绝；
- 变更动作之间保留 300-800ms 自然间隔。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Any

from . import policy, risk
from .session import BrowserSession
from .snapshot import build_snapshot

_NAVIGATE_TIMEOUT_MS = 30_000
_ACTION_TIMEOUT_MS = 10_000
_SETTLE_SECONDS = 0.6
_CLICK_PACING = (0.3, 0.8)
# 提交幂等锁冷却（031 §13.5）：同一按钮+同一 URL 在此窗口内只放行一次
_SUBMIT_COOLDOWN_SECONDS = 120

logger = logging.getLogger("divine.browser.engine")

_VALID_SCHEMES = ("http://", "https://")


def _error(message: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "message": message, **extra}


def _ok(payload: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, **payload}


async def _settle(page: Any, seconds: float = _SETTLE_SECONDS) -> None:
    await asyncio.sleep(seconds)


async def _pace() -> None:
    await asyncio.sleep(random.uniform(*_CLICK_PACING))  # noqa: S311 — 仅节奏抖动


def _ref_meta(session: BrowserSession, ref: str) -> dict[str, str] | None:
    return session.refs.get(str(ref or "").strip())


async def _snapshot_payload(session: BrowserSession, page: Any, ref: str | None = None) -> dict[str, Any]:
    result = await build_snapshot(session, page, ref)
    if not result.get("success"):
        return result
    attachment = policy.policy_attachment(result.get("url") or "", result.get("snapshot") or "")
    if attachment:
        result["policy"] = json.loads(attachment)["policy"]
    return result


async def op_navigate(
    session: BrowserSession, workspace: Path, url: str
) -> dict[str, Any]:
    url = str(url or "").strip()
    if not url.startswith(_VALID_SCHEMES):
        return _error("仅支持 http/https URL", rejected=True)
    blocked = policy.blocked_domain_hit(url)
    if blocked:
        return risk.refusal_payload(
            f"域名「{blocked}」在禁止名单（browser_blocked_domains 设置），已拒绝导航",
            risk="blocked-domain",
        )
    page = await session.ensure()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=_NAVIGATE_TIMEOUT_MS)
    except Exception as exc:  # noqa: BLE001 — 导航失败要回传给模型
        return _error(f"导航失败: {type(exc).__name__}: {str(exc)[:200]}")
    await _settle(page)
    session.refs.clear()  # 新页面，旧 ref 全部作废
    return await _snapshot_payload(session, page)


async def op_snapshot(
    session: BrowserSession, workspace: Path, ref: str | None = None
) -> dict[str, Any]:
    page = await session.ensure()
    return await _snapshot_payload(session, page, ref or None)


async def op_click(
    session: BrowserSession, workspace: Path, ref: str, intent: str | None = None
) -> dict[str, Any]:
    meta = _ref_meta(session, ref)
    if meta is None:
        return _error(
            f"编号 {ref} 不存在或已过期，请重新 browser_snapshot 获取最新页面",
            rejected=True,
        )
    level, hit = risk.classify_action(meta.get("name") or "", risk.normalize_intent(intent))
    if level == "irreversible" and not session.confirmed:
        return risk.refusal_payload(
            f"「{meta.get('name') or meta.get('role')}」判定为不可逆变更"
            + (f"（命中高风险词条「{hit}」）" if hit else "")
            + "。不可逆动作必须隔离在独立委派段：先以 confirmed=false 的委派完成"
            "信息抽取，由主 agent 渲染操作确认卡并获用户确认后，再以 "
            "web_task(confirmed=true) 委派执行本操作",
            risk="irreversible",
            target=meta.get("name") or "",
        )
    page = await session.ensure()
    # 提交幂等锁（031 §13.5）：同按钮+同 URL 冷却期内拒绝重复提交，失败只查不重提
    idem_key = f"{page.url}|{meta.get('name') or ''}"
    if (
        level == "irreversible"
        and session.last_submission is not None
        and session.last_submission[0] == idem_key
        and time.time() - session.last_submission[1] < _SUBMIT_COOLDOWN_SECONDS
    ):
        remaining = int(_SUBMIT_COOLDOWN_SECONDS - (time.time() - session.last_submission[1]))
        return risk.refusal_payload(
            f"「{meta.get('name')}」在 {remaining}s 内已提交过（幂等锁），不要重复提交——"
            "请用 browser_wait / browser_extract 查结果页确认是否已生效",
            risk="idempotent",
            target=meta.get("name") or "",
        )
    # 用户「每次确认」名单：该域名的任何变更动作都必须在 confirmed 委派段
    if not session.confirmed and policy.in_confirm_domains(page.url):
        return risk.refusal_payload(
            "该站点在「每次确认」名单（browser_confirm_domains 设置）：变更动作必须"
            "由用户在确认卡确认后以 web_task(confirmed=true) 委派执行",
            risk="confirm-domain",
            target=meta.get("name") or "",
        )
    locator = page.locator(meta["selector"])
    try:
        if await locator.count() == 0:
            return _error(
                f"编号 {ref} 对应元素已不在页面，请重新 browser_snapshot",
                rejected=True,
            )
        await _pace()
        await locator.click(timeout=_ACTION_TIMEOUT_MS)
    except Exception as exc:  # noqa: BLE001
        return _error(f"点击失败: {type(exc).__name__}: {str(exc)[:200]}")
    if level == "irreversible":
        session.last_submission = (idem_key, time.time())
    await _settle(page)
    return await _snapshot_payload(session, page)


async def op_fill(
    session: BrowserSession, workspace: Path, ref: str, text: str, intent: str | None = None
) -> dict[str, Any]:
    meta = _ref_meta(session, ref)
    if meta is None:
        return _error(
            f"编号 {ref} 不存在或已过期，请重新 browser_snapshot 获取最新页面",
            rejected=True,
        )
    cred = risk.credential_hit(meta.get("name") or "")
    if cred:
        return risk.refusal_payload(
            f"目标字段「{meta.get('name')}」命中凭据词典（{cred}）："
            "禁止输入任何密码/验证码/API key 类信息，此操作无条件拒绝",
            risk="credential",
            target=meta.get("name") or "",
        )
    page = await session.ensure()
    # 用户「每次确认」名单：该域名的任何变更动作都必须在 confirmed 委派段
    if not session.confirmed and policy.in_confirm_domains(page.url):
        return risk.refusal_payload(
            "该站点在「每次确认」名单（browser_confirm_domains 设置）：变更动作必须"
            "由用户在确认卡确认后以 web_task(confirmed=true) 委派执行",
            risk="confirm-domain",
            target=meta.get("name") or "",
        )
    locator = page.locator(meta["selector"])
    try:
        if await locator.count() == 0:
            return _error(
                f"编号 {ref} 对应元素已不在页面，请重新 browser_snapshot",
                rejected=True,
            )
        await _pace()
        await locator.fill(str(text or ""), timeout=_ACTION_TIMEOUT_MS)
    except Exception as exc:  # noqa: BLE001
        return _error(f"输入失败: {type(exc).__name__}: {str(exc)[:200]}")
    await _settle(page)
    return await _snapshot_payload(session, page)


async def op_select(
    session: BrowserSession, workspace: Path, ref: str, option: str
) -> dict[str, Any]:
    meta = _ref_meta(session, ref)
    if meta is None:
        return _error(
            f"编号 {ref} 不存在或已过期，请重新 browser_snapshot 获取最新页面",
            rejected=True,
        )
    page = await session.ensure()
    locator = page.locator(meta["selector"])
    try:
        if await locator.count() == 0:
            return _error(
                f"编号 {ref} 对应元素已不在页面，请重新 browser_snapshot",
                rejected=True,
            )
        await _pace()
        # 优先按可见文本匹配，其次 value
        try:
            await locator.select_option(label=str(option), timeout=_ACTION_TIMEOUT_MS)
        except Exception:  # noqa: BLE001 — 文本匹配失败退回 value
            await locator.select_option(value=str(option), timeout=_ACTION_TIMEOUT_MS)
    except Exception as exc:  # noqa: BLE001
        return _error(f"选择失败: {type(exc).__name__}: {str(exc)[:200]}")
    await _settle(page)
    return await _snapshot_payload(session, page)


async def op_scroll(
    session: BrowserSession, workspace: Path, direction: str, amount: int | None = None
) -> dict[str, Any]:
    page = await session.ensure()
    pixels = int(amount or 600)
    delta = pixels if str(direction).lower() != "up" else -pixels
    try:
        await page.mouse.wheel(0, delta)
    except Exception as exc:  # noqa: BLE001
        return _error(f"滚动失败: {type(exc).__name__}")
    await _settle(page, 0.3)
    return await _snapshot_payload(session, page)


async def op_extract(
    session: BrowserSession,
    workspace: Path,
    ref: str | None = None,
    selectors: dict[str, str] | None = None,
) -> dict[str, Any]:
    page = await session.ensure()
    payload: dict[str, Any] = {}

    if ref:
        meta = _ref_meta(session, ref)
        if meta is None:
            return _error(
                f"编号 {ref} 不存在或已过期，请重新 browser_snapshot",
                rejected=True,
            )
        locator = page.locator(meta["selector"])
        try:
            if await locator.count() == 0:
                return _error(f"编号 {ref} 对应元素已不在页面", rejected=True)
            payload["element"] = {
                "text": (await locator.inner_text(timeout=_ACTION_TIMEOUT_MS))[:8000],
            }
            href = await locator.get_attribute("href", timeout=_ACTION_TIMEOUT_MS)
            if href:
                payload["element"]["href"] = href
        except Exception as exc:  # noqa: BLE001
            return _error(f"抽取失败: {type(exc).__name__}: {str(exc)[:200]}")

    for name, css in (selectors or {}).items():
        try:
            values = await page.locator(str(css)).all_inner_texts()
            payload[str(name)] = [v.strip()[:300] for v in values[:50] if v.strip()]
        except Exception as exc:  # noqa: BLE001 — 单个选择器失败不拖垮整体
            payload[str(name)] = {"error": type(exc).__name__}

    result = _ok({"data": payload, "url": page.url})
    attachment = policy.policy_attachment(page.url, json.dumps(payload, ensure_ascii=False))
    if attachment:
        result["policy"] = json.loads(attachment)["policy"]
    return result


async def op_wait(
    session: BrowserSession,
    workspace: Path,
    condition: dict[str, Any],
    timeout: int | None = None,
) -> dict[str, Any]:
    page = await session.ensure()
    timeout_ms = max(1, min(int(timeout or 15), 60)) * 1000
    try:
        if condition.get("selector"):
            await page.wait_for_selector(
                str(condition["selector"]), state="visible", timeout=timeout_ms
            )
        elif condition.get("text"):
            await page.wait_for_selector(
                f"text={condition['text']}", state="visible", timeout=timeout_ms
            )
        elif condition.get("url_contains"):
            fragment = str(condition["url_contains"])
            deadline = time.monotonic() + timeout_ms / 1000
            while time.monotonic() < deadline:
                if fragment in (page.url or ""):
                    break
                await asyncio.sleep(0.5)
            else:
                return _error(f"等待超时（{timeout_ms // 1000}s）：URL 未包含 {fragment}")
        else:
            return _error(
                "condition 需要提供 selector / text / url_contains 之一", rejected=True
            )
    except Exception as exc:  # noqa: BLE001
        return _error(f"等待超时或失败: {type(exc).__name__}: {str(exc)[:200]}")
    return await _snapshot_payload(session, page)


_KEY_EXPR_RE = re.compile(r"[A-Za-z0-9+]{1,20}")


async def op_press_key(
    session: BrowserSession, workspace: Path, key: str, ref: str | None = None
) -> dict[str, Any]:
    """向焦点元素（可先按 ref 聚焦）发送键盘按键，返回新快照。

    用途：回车提交、Tab 焦点遍历、方向键选择、Escape 关浮层——
    覆盖无 ref 可点的惰性控件与富文本编辑器场景。
    注意：回车/Tab 可能触发表单提交，提交类按键只应出现在 confirmed=true 委派段
    （提示纪律约束，词典无法覆盖键盘语义）。
    """
    key_expr = str(key or "").strip()
    if not _KEY_EXPR_RE.fullmatch(key_expr):
        return _error(
            "不支持的按键表达式（允许 Enter / Tab / Escape / ArrowDown / Control+A 等字母数字组合）",
            rejected=True,
        )
    page = await session.ensure()
    if ref:
        meta = _ref_meta(session, ref)
        if meta is None:
            return _error(
                f"编号 {ref} 不存在或已过期，请重新 browser_snapshot 获取最新页面",
                rejected=True,
            )
        locator = page.locator(meta["selector"])
        try:
            if await locator.count() == 0:
                return _error(f"编号 {ref} 对应元素已不在页面", rejected=True)
            await locator.focus(timeout=_ACTION_TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001
            return _error(f"聚焦失败: {type(exc).__name__}: {str(exc)[:200]}")
    await _pace()
    try:
        await page.keyboard.press(key_expr)
    except Exception as exc:  # noqa: BLE001
        return _error(f"按键失败: {type(exc).__name__}: {str(exc)[:200]}")
    await _settle(page)
    return await _snapshot_payload(session, page)


async def op_read_page(session: BrowserSession, workspace: Path) -> dict[str, Any]:
    """元素截图 → 视觉模型 caption（031 §4 caption 路径）。

    MVP：截图落盘（JPEG 1280×800 viewport，禁全页长图）并回传路径；
    视觉描述模型未配置时降级返回页面可见文本摘要，提示快照优先。
    """
    page = await session.ensure()
    try:
        from ...config import output_dir_for_workspace

        out_dir = output_dir_for_workspace(workspace)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"browser-page-{time.strftime('%H%M%S')}-{random.randint(100, 999)}.jpg"  # noqa: S311
        await page.screenshot(
            path=str(path), type="jpeg", quality=70, full_page=False
        )
    except Exception as exc:  # noqa: BLE001
        return _error(f"截图失败: {type(exc).__name__}: {str(exc)[:200]}")

    caption = await _vision_caption(path)
    if caption:
        return _ok({"message": "页面截图（视觉描述）", "caption": caption, "filepath": str(path)})

    # 降级：可见文本摘要（快照已含结构，文本只做视觉盲区兜底）
    try:
        visible = await page.evaluate(
            "() => (document.body ? document.body.innerText : '').slice(0, 4000)"
        )
    except Exception:  # noqa: BLE001
        visible = ""
    return _ok(
        {
            "message": "已保存页面截图；视觉描述模型未配置，返回可见文本摘要",
            "filepath": str(path),
            "visible_text": visible,
        }
    )


async def _vision_caption(image_path: Path) -> str | None:
    """视觉描述：优先会话多模态模型，其次 GLM 视觉（GLM-4V 免费）。

    供 `browser_read_page` 的 caption 路径使用（031 §4）；未配置或调用失败
    返回 None，调用方降级为可见文本摘要。
    """
    try:
        import base64

        import httpx

        from ...config import settings_store
        from ..scripts.read_image import _resolve_glm, _resolve_vision_provider

        settings = settings_store.load()
        resolved = _resolve_vision_provider(settings, None)
        if resolved is not None:
            api_key, base_url, model, _is_session = resolved
        else:
            glm = _resolve_glm(settings)
            if glm is None:
                return None
            api_key, base_url, model = glm
        if not (api_key and base_url):
            return None

        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        response = await httpx.AsyncClient(timeout=30.0).post(
            base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    "用简洁中文描述这个网页截图：页面主题、主要区块、"
                                    "可操作元素（按钮/输入框/链接）。120 字以内。"
                                ),
                            },
                        ],
                    }
                ],
                "max_tokens": 300,
            },
        )
        response.raise_for_status()
        caption = str(response.json()["choices"][0]["message"]["content"] or "").strip()
        return caption or None
    except Exception as exc:  # noqa: BLE001 — caption 失败必须降级而非报错
        logger.warning("vision caption failed: %s: %s", type(exc).__name__, str(exc)[:120])
        return None
