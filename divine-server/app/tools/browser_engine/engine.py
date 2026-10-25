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


_LOGIN_BARRIER_JS = r"""
() => {
  const tel = document.querySelector(
    'input[type=tel], input[name*=phone i], input[placeholder*=手机], input[name*=mobile i]'
  );
  const pwd = document.querySelector('input[type=password]');
  const code = document.querySelector(
    'input[autocomplete=one-time-code], input[name*=code i], input[name*=captcha i], input[placeholder*=验证码]'
  );
  const getCodeBtn = [...document.querySelectorAll("button, a, span, div")].find(
    (el) => /获取验证码|发送验证码|获取短信/.test(el.innerText || "") && el.offsetWidth > 0
  );

  // 登录方式枚举（032 §3 L1）：可见的页签/按钮文本 + 表单字段推断
  const METHOD_PATTERNS = [
    { type: "qr",      re: /扫码|二维码|QR/i },
    { type: "sms",     re: /短信|验证码登录|手机号登录/ },
    { type: "password", re: /密码登录|账号登录|账密/ },
    { type: "oauth",   re: /微信|支付宝|QQ|Apple|苹果/i },
  ];
  const seen = new Set();
  const methods = [];
  const candidates = [...document.querySelectorAll("a, button, span, div, li, tab")];
  for (const el of candidates) {
    if (el.offsetWidth <= 0 || el.offsetHeight <= 0) continue;
    const text = (el.innerText || "").trim();
    if (!text || text.length > 12) continue;
    for (const p of METHOD_PATTERNS) {
      if (p.re.test(text) && !seen.has(p.type + ":" + text)) {
        seen.add(p.type + ":" + text);
        // 取最短匹配容器（页签文本），避免外层大 div 重复计入
        if (!methods.some((m) => m.type === p.type)) {
          methods.push({ type: p.type, label: text });
        }
      }
    }
  }
  // 表单字段推断（当前面板实际渲染的方式）
  if (pwd && !methods.some((m) => m.type === "password")) {
    methods.push({ type: "password", label: "密码登录（当前面板）" });
  }
  if (tel && (code || getCodeBtn) && !methods.some((m) => m.type === "sms")) {
    methods.push({ type: "sms", label: "短信验证码登录（当前面板）" });
  }

  if (!pwd && !(tel && (code || getCodeBtn)) && methods.length === 0) return null;
  return {
    has_password: !!pwd,
    has_phone: !!tel,
    has_code: !!code,
    has_get_code_btn: !!getCodeBtn,
    login_methods: methods,
  };
}
"""


async def _login_barrier(page: Any) -> dict[str, Any] | None:
    """登录屏障检测（032 §3 L1）：登录表单启发式，命中则返回结构化信息。"""
    try:
        return await page.evaluate(_LOGIN_BARRIER_JS)
    except Exception:  # noqa: BLE001 — 检测失败不影响导航本身
        return None


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
    session.last_navigated_url = url  # 断点：模式切换/自愈重启后自动重导航
    # 登录屏障检测（032 §3 L1）：命中则让模型干净地结束委派段去走登录卡片
    barrier = await _login_barrier(page)
    result = await _snapshot_payload(session, page)
    if barrier and result.get("success"):
        result["login_barrier"] = barrier
        methods = barrier.get("login_methods") or []
        if len(methods) > 1:
            result["message"] = (
                "检测到登录页，且存在多种登录方式："
                + "、".join(f"{m.get('label')}（{m.get('type')}）" for m in methods)
                + "。请结束本委派段，把 login_barrier 回传主 agent——"
                "**由用户选择登录方式**（ask_user 选项卡），选定后再按对应流程委派："
                "qr=截码展示等待扫码 / sms=登录卡片收手机号与验证码 / "
                "password=密码方式选择卡 / oauth=通常需有头浮窗人工点击"
            )
        else:
            result["message"] = (
                "检测到登录表单：请结束本委派段，把 login_barrier 结构回传主 agent"
                "渲染登录卡片（收集手机号/验证码后以 confirmed=true 委派填入）"
            )
    return result


async def op_snapshot(
    session: BrowserSession, workspace: Path, ref: str | None = None
) -> dict[str, Any]:
    page = await session.ensure()
    return await _snapshot_payload(session, page, ref or None)


async def op_click(
    session: BrowserSession,
    workspace: Path,
    ref: str | None = None,
    text: str | None = None,
    intent: str | None = None,
    selectors: dict[str, str] | None = None,
) -> dict[str, Any]:
    """点击元素：ref 优先，text 兜底（移动端 H5 的纯文本卡片无 role/ref 可寻），
    selectors 再兜底（图片绘制的无障碍盲区按钮，如美团的「+」加购图标——
    用配方/extract 给出的 CSS 定位）。

    text 按可见文本（支持部分匹配）定位元素后点击——事件会冒泡到框架的
    委托根节点，因此对 React/Vue 委托绑定的卡片同样生效。风险判定不变：
    可见文本命中高风险词典照样拦截；selector 点击无语义名称，依赖 intent
    标注 + 幂等锁 + confirmed 委派段。
    """
    element_name = ""
    meta: dict[str, str] | None = None
    if ref:
        meta = _ref_meta(session, ref)
        if meta is None:
            return _error(
                f"编号 {ref} 不存在或已过期，请重新 browser_snapshot 获取最新页面"
                "；若是快照里的纯文本节点（无 ref），可改用 text 参数按可见文本点击",
                rejected=True,
            )
        element_name = meta.get("name") or ""
    elif (text or "").strip():
        element_name = str(text).strip()
    elif selectors:
        first_css = next(iter(selectors.values()), "")
        element_name = f"css:{first_css}"
    else:
        return _error(
            "需要 ref / text / selectors 之一（ref 优先；无 role 纯文本用 text；"
            "无障碍盲区的图片按钮用 selectors）",
            rejected=True,
        )

    level, hit = risk.classify_action(element_name, risk.normalize_intent(intent))
    if level == "irreversible" and not session.confirmed:
        return risk.refusal_payload(
            f"「{element_name or '目标元素'}」判定为不可逆变更"
            + (f"（命中高风险词条「{hit}」）" if hit else "")
            + "。不可逆动作必须隔离在独立委派段：先以 confirmed=false 的委派完成"
            "信息抽取，由主 agent 渲染操作确认卡并获用户确认后，再以 "
            "web_task(confirmed=true) 委派执行本操作",
            risk="irreversible",
            target=element_name,
        )
    page = await session.ensure()
    # 提交幂等锁（031 §13.5）：同按钮+同 URL 冷却期内拒绝重复提交，失败只查不重提
    idem_key = f"{page.url}|{element_name}"
    if (
        level == "irreversible"
        and session.last_submission is not None
        and session.last_submission[0] == idem_key
        and time.time() - session.last_submission[1] < _SUBMIT_COOLDOWN_SECONDS
    ):
        remaining = int(_SUBMIT_COOLDOWN_SECONDS - (time.time() - session.last_submission[1]))
        return risk.refusal_payload(
            f"「{element_name}」在 {remaining}s 内已提交过（幂等锁），不要重复提交——"
            "请用 browser_wait / browser_extract 查结果页确认是否已生效",
            risk="idempotent",
            target=element_name,
        )
    # 用户「每次确认」名单：该域名的任何变更动作都必须在 confirmed 委派段
    if not session.confirmed and policy.in_confirm_domains(page.url):
        return risk.refusal_payload(
            "该站点在「每次确认」名单（browser_confirm_domains 设置）：变更动作必须"
            "由用户在确认卡确认后以 web_task(confirmed=true) 委派执行",
            risk="confirm-domain",
            target=element_name,
        )
    if meta is not None:
        locator = page.locator(meta["selector"])
    elif selectors:
        css = next(iter(selectors.values()), "")
        locator = page.locator(css).first
    else:
        locator = page.get_by_text(element_name, exact=False).first
    try:
        if await locator.count() == 0:
            hint = (
                "请重新 browser_snapshot 获取最新页面"
                if meta is not None
                else "确认文本与快照里的可见文本一致（可只给部分文本）"
            )
            return _error(f"目标元素不在页面上：{hint}", rejected=True)
        await _pace()
        pages_before = session.page_ids()
        await locator.click(timeout=_ACTION_TIMEOUT_MS)
        # target=_blank 新标签页自动接管（H5 点单/外链普遍形态），
        # 否则引擎会绑在旧 tab 上、快照不变，模型陷入无限重试
        if await session.adopt_new_page(pages_before):
            page = await session.ensure()
        if level == "irreversible":
            session.last_submission = (idem_key, time.time())
    except Exception as exc:  # noqa: BLE001
        return _error(f"点击失败: {type(exc).__name__}: {str(exc)[:200]}")
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
    field = meta.get("name") or ""
    # 无条件拒绝类：卡片 PIN/CVV/API key——agent 永远没有填它们的正当场景
    if risk.always_secret_hit(field):
        return risk.refusal_payload(
            f"目标字段「{field}」为卡片安全码/API key 类：无条件拒绝输入（032 §5），"
            "此类凭据不存在可放行的场景",
            risk="credential",
            target=field,
        )
    # 登录密码类（032 §5 修订）：confirmed=true 委派段可填，两种方式由用户在
    # 对话流里选择——直接填（密码经对话上下文发给云端模型）或密钥把手
    # （secret:xxx 引用，前端直存后端内存，密码不接触模型）；
    # 未确认段仍拒绝。卡片 PIN/CVV/API key 无条件拒绝（always_secret_hit）。
    is_password = risk.password_hit(field)
    code_term = risk.code_hit(field)
    if (is_password or code_term) and not session.confirmed:
        kind = "密码" if is_password else "验证码"
        return risk.refusal_payload(
            f"目标字段「{field}」为{kind}类字段：仅允许在用户经登录卡片提供"
            "凭据后的 confirmed=true 委派段中填入（032 §5）。"
            "当前为 confirmed=false 委派段，请结束本委派段并回传登录表单结构",
            risk="credential",
            target=field,
        )
    page = await session.ensure()
    # 密钥把手模式（032 §5，对话流里用户选择）：fill 值为 secret:<hex> 时由
    # 后端内存存储解析真实值——明文不进对话上下文/日志，一次性销毁
    fill_value = str(text or "")
    if fill_value.startswith("secret:"):
        from .secrets import resolve_secret

        resolved = resolve_secret(fill_value)
        if resolved is None:
            return _error(
                "密钥把手无效或已过期（一次性、10 分钟 TTL）：请让用户重新在登录卡片提交",
                rejected=True,
            )
        fill_value = resolved
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
        await locator.fill(fill_value, timeout=_ACTION_TIMEOUT_MS)
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
    pages_before = session.page_ids()
    try:
        await page.keyboard.press(key_expr)
    except Exception as exc:  # noqa: BLE001
        return _error(f"按键失败: {type(exc).__name__}: {str(exc)[:200]}")
    if await session.adopt_new_page(pages_before):
        page = await session.ensure()
    await _settle(page)
    return await _snapshot_payload(session, page)


async def op_track_order(
    session: BrowserSession,
    workspace: Path,
    marker: str,
    timeout_minutes: int | None = None,
    interval_seconds: int | None = None,
) -> dict[str, Any]:
    """启动订单状态后台轮询（031 §14.2 第 9 步）。

    用于 confirmed 委派段提交订单后：每个 interval 重新加载当前页检查
    marker 文本（如「支付成功」「订单已提交」），命中/超时经常驻事件流
    广播 ``browser_order`` 事件——回合结束后轮询继续，不占委派段生命周期。
    """
    marker_text = str(marker or "").strip()
    if not marker_text:
        return _error("marker 不能为空：给出订单页成功状态的标记文本（如「支付成功」）", rejected=True)
    timeout_s = max(60, min(int(timeout_minutes or 15), 60)) * 60
    interval = max(10, min(int(interval_seconds or 60), 300))
    started = await session.start_order_watch(
        marker_text, session.key, interval_s=interval, timeout_s=timeout_s
    )
    if not started:
        return _error("该会话已有进行中的订单追踪，请先等待其结束或取消", rejected=True)
    return _ok(
        {
            "message": (
                f"订单追踪已启动：每 {interval}s 检查一次「{marker_text}」，"
                f"最长 {timeout_s // 60} 分钟；命中/超时经事件流通知。"
                "现在可以结束本轮汇报，等待支付完成后的事件通知。"
            ),
            "marker": marker_text,
            "timeout_s": timeout_s,
        }
    )


async def op_read_captcha(
    session: BrowserSession, workspace: Path, ref: str
) -> dict[str, Any]:
    """图形验证码识别（032 §3 L2）：验证码元素截图 → 视觉模型 → 返回字符。

    识别结果交给模型在 confirmed 委派段内经 browser_fill 填入；
    视觉模型未配置/识别失败时返回 code=None，模型降级为登录卡片人工认读。
    """
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
            return _error(f"编号 {ref} 对应元素已不在页面", rejected=True)
        from ...config import output_dir_for_workspace

        out_dir = output_dir_for_workspace(workspace) / "browser"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"captcha-{time.strftime('%H%M%S')}-{random.randint(100, 999)}.jpg"  # noqa: S311
        await locator.screenshot(path=str(path), type="jpeg", quality=90)
    except Exception as exc:  # noqa: BLE001
        return _error(f"验证码截图失败: {type(exc).__name__}: {str(exc)[:200]}")

    code = None
    try:
        code = await _vision_caption(
            path,
            prompt="识别图片中的验证码，只输出验证码字符本身（字母/数字），不要任何其他内容。",
            model_id=getattr(session, "model_id", None),
        )
    except Exception:  # noqa: BLE001 — 识别异常与识别失败同等处理
        code = None

    cleaned = re.sub(r"[^A-Za-z0-9]", "", code or "")[:8]
    if cleaned:
        # 识别成功：截图是一次性输入，用完即删
        try:
            path.unlink(missing_ok=True)
        except OSError:  # noqa: BLE001
            pass
        return _ok({"code": cleaned, "message": "验证码识别成功"})

    # 识别失败：截图**保留**并返回现成 markdown——主 agent 把图片嵌进回复
    # （与二维码同机制），用 ask_user 收用户认读的验证码，再 confirmed 段填入
    return _ok(
        {
            "code": None,
            "filepath": str(path),
            "markdown": f"![验证码]({path})",
            "message": (
                "验证码自动识别失败：把 result 里的 markdown 字段**逐字原样**嵌进"
                "回复正文展示验证码图片，并用 ask_user 请用户输入图中字符；"
                "收到后以 confirmed=true 委派填入。不要反复重试识别"
            ),
        }
    )


async def op_capture(
    session: BrowserSession,
    workspace: Path,
    ref: str | None = None,
    selector: str | None = None,
    name: str = "capture",
) -> dict[str, Any]:
    """元素截图并**持久化**到工作区 browser/（032 扫码登录支持）。

    与 browser_read_page 的区别：read_page 截图是视觉描述的一次性输入（用完即删）；
    capture 保留文件并返回绝对路径——主 agent 在正文里嵌 `![二维码](路径)`
    即可把二维码渲染进对话流，用户手机扫码，无头模式全程无需开窗口。
    """
    page = await session.ensure()
    if ref:
        meta = _ref_meta(session, ref)
        if meta is None:
            return _error(
                f"编号 {ref} 不存在或已过期，请重新 browser_snapshot", rejected=True
            )
        locator = page.locator(meta["selector"])
    elif (selector or "").strip():
        locator = page.locator(selector.strip()).first
    else:
        locator = None  # 兜底：整 viewport 截图（031 禁全页长图，viewport 可以）
    try:
        from ...config import output_dir_for_workspace

        out_dir = output_dir_for_workspace(workspace) / "browser"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^\w\-]", "", str(name))[:20] or "capture"
        path = out_dir / f"{safe_name}-{time.strftime('%H%M%S')}-{random.randint(100, 999)}.png"  # noqa: S311
        if locator is not None:
            if await locator.count() == 0:
                return _error("目标元素不在页面上", rejected=True)
            await locator.screenshot(path=str(path))
        else:
            await page.screenshot(path=str(path), full_page=False)
    except Exception as exc:  # noqa: BLE001
        return _error(f"截图失败: {type(exc).__name__}: {str(exc)[:200]}")
    return _ok(
        {
            "message": "截图已保存（持久化，可嵌入对话）",
            "filepath": str(path),
            # 现成可粘贴的 markdown：主 agent 原样放进回复正文即显示图片
            "markdown": f"![二维码]({path})",
            "hint": (
                "把 result 里的 markdown 字段**逐字原样**放进你的回复正文（文件名里的"
                "时间戳是防覆盖设计，**禁止改写/简化文件路径**——改了路径图片就 404 "
                "不显示）；展示后立即 browser_wait 登录成功标记"
                "（timeout 120-180s），过期则刷新二维码重截（≤2 次）"
            ),
        }
    )


_SNIFF_STATIC_RE = re.compile(
    r"\.(js|css|png|jpe?g|gif|svg|woff2?|ttf|ico|mp4|webp)(\?|$)", re.IGNORECASE
)


async def op_sniff_start(
    session: BrowserSession, workspace: Path, pattern: str
) -> dict[str, Any]:
    """开始嗅探匹配 pattern（正则）的网络请求（032 §6 API 模拟登录第 1 步）。

    子 Agent 随后在页面上执行操作（UI 登录/提交），引擎记录匹配的 XHR/fetch；
    browser_sniff_stop 取回捕获的请求模板（method/url/status/post_data）。
    """
    try:
        session.sniff_pattern = re.compile(str(pattern or ""))
    except re.error as exc:
        return _error(f"pattern 不是合法正则: {exc}", rejected=True)
    session.sniff_records = []
    page = await session.ensure()

    def on_response(response: Any) -> None:
        try:
            url = response.url
            if session.sniff_pattern is None or not session.sniff_pattern.search(url):
                return
            if _SNIFF_STATIC_RE.search(url):
                return
            req = response.request
            session.sniff_records.append(
                {
                    "url": url,
                    "method": req.method,
                    "status": response.status,
                    "post_data": req.post_data,
                    "resource_type": req.resource_type,
                }
            )
            if len(session.sniff_records) > 50:
                session.sniff_records = session.sniff_records[-50:]
        except Exception:  # noqa: BLE001 — 单条记录失败不影响捕获
            pass

    page.on("response", on_response)
    session.sniff_handler = on_response
    return _ok(
        {
            "message": (
                f"嗅探已开始（pattern={pattern}）：现在执行页面操作，"
                "完成后 browser_sniff_stop 取回请求模板"
            )
        }
    )


async def op_sniff_stop(session: BrowserSession, workspace: Path) -> dict[str, Any]:
    """停止嗅探并返回捕获的请求记录（模板）。"""
    page = await session.ensure()
    handler = getattr(session, "sniff_handler", None)
    if handler is not None:
        try:
            page.remove_listener("response", handler)
        except Exception:  # noqa: BLE001
            pass
        session.sniff_handler = None
    records = session.sniff_records
    session.sniff_records = []
    session.sniff_pattern = None
    return _ok(
        {
            "count": len(records),
            "records": records,
            "hint": (
                "找出登录请求（POST + JSON/表单体 + 2xx）：若 body 是明文手机号/"
                "密码/验证码字段（无加密摘要/签名），可由主 agent ask_user 收凭据后"
                " browser_api_login(confirmed=true) 重放；body 含加密密码或动态"
                "签名则放弃 API 路线，回退 UI 登录流程"
            ),
        }
    )


async def op_api_login(
    session: BrowserSession,
    workspace: Path,
    url: str,
    method: str = "POST",
    body: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """API 模拟登录（032 §6，仅 confirmed=true 委派段）。

    重放嗅探到的登录请求（httpx），把响应 Set-Cookie 注入浏览器上下文，
    实现"不开 UI、不碰验证码"的会话恢复。安全约束：
    - 目标 URL 域必须与当前任务页面同域（防凭据外送）；
    - 携凭据的请求必须在 confirmed 委派段（与 UI 填入同级）。
    """
    if not session.confirmed:
        return risk.refusal_payload(
            "API 模拟登录（请求体含凭据）仅允许在 confirmed=true 委派段执行",
            risk="confirmed",
        )
    from urllib.parse import urlparse

    target = str(url or "").strip()
    if not target.startswith(_VALID_SCHEMES):
        return _error("仅支持 http/https URL", rejected=True)
    page = await session.ensure()
    page_host = urlparse(page.url or "").hostname or ""
    target_host = urlparse(target).hostname or ""
    if not page_host or not target_host or target_host != page_host:
        return _error(
            f"重放目标域（{target_host}）必须与当前任务页面域（{page_host}）一致——"
            "防止凭据被发送到第三方接口",
            rejected=True,
        )
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = await client.request(
                str(method or "POST").upper(),
                target,
                content=body,
                headers={"Content-Type": "application/json", **(headers or {})},
            )
    except Exception as exc:  # noqa: BLE001
        return _error(f"重放请求失败: {type(exc).__name__}: {str(exc)[:200]}")

    cookies_to_inject = [
        {"name": name, "value": value, "url": target}
        for name, value in response.cookies.items()
    ]
    injected = 0
    if cookies_to_inject:
        try:
            await page.context.add_cookies(cookies_to_inject)
            injected = len(cookies_to_inject)
        except Exception as exc:  # noqa: BLE001 — 注入失败仍返回响应，便于诊断
            logger.warning("cookie 注入失败: %s", exc)
    body_preview = response.text[:600]
    ok = 200 <= response.status_code < 300
    return _ok(
        {
            "status": response.status_code,
            "cookies_injected": injected,
            "body_preview": body_preview,
            "message": (
                f"重放成功（HTTP {response.status_code}，注入 {injected} 个 cookie）——"
                "请 browser_snapshot 验证登录态；若 body 提示验证码/签名错误，"
                "说明该站不适合 API 路线，回退 UI 登录"
                if ok
                else f"重放返回 HTTP {response.status_code}：查看 body_preview 判断原因，通常回退 UI 登录"
            ),
        }
    )


async def op_api_call(
    session: BrowserSession,
    workspace: Path,
    url: str,
    method: str = "GET",
    body: str | None = None,
    headers: dict[str, str] | None = None,
    send_cookies: bool = True,
    inject_cookies: bool = False,
) -> dict[str, Any]:
    """站点 API 通用调用（032 §6）：登录/注册/数据接口的统一通道。

    与浏览器 UI 平行的能力面——嗅探到的任何同站接口都可重放：
    - 数据获取：GET/HEAD（只读级）无需 confirmed，自动附浏览器登录态 cookie；
    - 登录/注册/变更：非 GET 或带 body（变更级）需 confirmed=true；
      inject_cookies=true 时把响应 Set-Cookie 注入浏览器（登录场景）。
    安全：目标域必须与当前任务页面同域（防凭据/cookie 外送）。
    """
    from urllib.parse import urlparse

    target = str(url or "").strip()
    if not target.startswith(_VALID_SCHEMES):
        return _error("仅支持 http/https URL", rejected=True)
    page = await session.ensure()
    page_host = urlparse(page.url or "").hostname or ""
    target_host = urlparse(target).hostname or ""
    if not page_host or not target_host or target_host != page_host:
        return _error(
            f"API 目标域（{target_host}）必须与当前任务页面域（{page_host}）一致——"
            "防止凭据/cookie 被发送到第三方接口",
            rejected=True,
        )
    method_upper = str(method or "GET").upper()
    mutating = method_upper not in ("GET", "HEAD") or bool((body or "").strip())
    if mutating and not session.confirmed:
        return risk.refusal_payload(
            f"{method_upper} 带 body 属变更级请求：仅允许在 confirmed=true 委派段执行"
            "（登录/注册/提交类）；只读数据获取用 GET 且不带 body",
            risk="confirmed",
        )

    import httpx

    req_headers = {"Content-Type": "application/json", **(headers or {})}
    if send_cookies:
        try:
            ctx_cookies = await page.context.cookies()
            # 注意不过滤 expires：Playwright 会话 cookie 的 expires=-1，
            # 按过期过滤会把登录态整个丢掉（实测 401）
            jar = "; ".join(f"{c['name']}={c['value']}" for c in ctx_cookies)
            if jar:
                req_headers.setdefault("Cookie", jar)
        except Exception as exc:  # noqa: BLE001 — cookie 读取失败按无登录态继续
            logger.warning("cookie 透传读取失败: %s", exc)
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            response = await client.request(
                method_upper, target, content=body, headers=req_headers
            )
    except Exception as exc:  # noqa: BLE001
        return _error(f"API 请求失败: {type(exc).__name__}: {str(exc)[:200]}")

    injected = 0
    if inject_cookies and response.cookies:
        try:
            await page.context.add_cookies(
                [
                    {"name": name, "value": value, "url": target}
                    for name, value in response.cookies.items()
                ]
            )
            injected = len(response.cookies)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cookie 注入失败: %s", exc)
    ok = 200 <= response.status_code < 300
    return _ok(
        {
            "status": response.status_code,
            "cookies_injected": injected,
            "body_preview": response.text[:2000],
            "message": (
                f"API 调用成功（HTTP {response.status_code}"
                + (f"，注入 {injected} 个 cookie" if injected else "")
                + "）——body_preview 为响应内容，按需解析字段"
                if ok
                else f"API 返回 HTTP {response.status_code}：查看 body_preview 判断原因"
            ),
        }
    )


async def op_geometry(
    session: BrowserSession,
    workspace: Path,
    selector: str | None = None,
    ref: str | None = None,
) -> dict[str, Any]:
    """元素几何信息（032 §3 补充）：bounding_box + devicePixelRatio。

    替代 JS evaluate 取 rect——Playwright 原生 bounding_box 无需任意 JS。
    """
    page = await session.ensure()
    if ref:
        meta = _ref_meta(session, ref)
        if meta is None:
            return _error(f"编号 {ref} 不存在或已过期，请重新 browser_snapshot", rejected=True)
        locator = page.locator(meta["selector"])
    elif (selector or "").strip():
        locator = page.locator(selector.strip()).first
    else:
        return _error("需要 selector 或 ref 之一", rejected=True)
    try:
        if await locator.count() == 0:
            return _error("元素不在页面上", rejected=True)
        box = await locator.bounding_box()
        if not box:
            return _error("元素不可见或无几何信息", rejected=True)
        dpr = await page.evaluate("window.devicePixelRatio")
    except Exception as exc:  # noqa: BLE001
        return _error(f"几何信息获取失败: {type(exc).__name__}: {str(exc)[:200]}")
    return _ok({"rect": box, "dpr": dpr})


async def op_solve_slider(
    session: BrowserSession,
    workspace: Path,
    handle_ref: str,
    track_ref: str,
    piece_ref: str | None = None,
    success_text: str | None = None,
) -> dict[str, Any]:
    """滑块验证码自动求解（032 §3 L2.5，实验性）。

    仅 confirmed=true 委派段（用户在场授权）。流程：滑轨/拼图元素截图 →
    Pillow 缺口识别（双图差分或列差分）→ 拟人轨迹拖拽（分段缓动+过冲+抖动）
    → 可选成功标记检测。失败由模型重试 ≤2 次后降级人工（L4）。
    """
    if not session.confirmed:
        return risk.refusal_payload(
            "滑块自动求解仅允许在 confirmed=true 委派段执行（用户在场授权，"
            "行为风控敏感操作）",
            risk="confirmed",
        )
    handle_meta = _ref_meta(session, handle_ref)
    track_meta = _ref_meta(session, track_ref)
    if handle_meta is None or track_meta is None:
        return _error(
            "手柄/滑轨 ref 不存在或已过期，请重新 browser_snapshot",
            rejected=True,
        )
    page = await session.ensure()
    handle_loc = page.locator(handle_meta["selector"])
    track_loc = page.locator(track_meta["selector"])
    try:
        if await handle_loc.count() == 0 or await track_loc.count() == 0:
            return _error("手柄或滑轨元素已不在页面", rejected=True)
        hb = await handle_loc.bounding_box()
        tb = await track_loc.bounding_box()
    except Exception as exc:  # noqa: BLE001
        return _error(f"定位失败: {type(exc).__name__}: {str(exc)[:200]}")
    if not hb or not tb:
        return _error("无法获取手柄/滑轨几何信息", rejected=True)

    from ...config import output_dir_for_workspace

    out_dir = output_dir_for_workspace(workspace) / "browser"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%H%M%S")
    track_png = out_dir / f"slider-track-{stamp}.png"
    piece_png: Path | None = None
    try:
        # scale="css"：截图像素与 CSS 像素 1:1，缺口距离直接可用
        await track_loc.screenshot(path=str(track_png), scale="css")
        if piece_ref:
            piece_meta = _ref_meta(session, piece_ref)
            if piece_meta is not None:
                ploc = page.locator(piece_meta["selector"])
                if await ploc.count() > 0:
                    piece_png = out_dir / f"slider-piece-{stamp}.png"
                    await ploc.screenshot(path=str(piece_png), scale="css")
    except Exception as exc:  # noqa: BLE001
        return _error(f"滑块截图失败: {type(exc).__name__}: {str(exc)[:200]}")

    from .slider import detect_gap_x, human_track

    search_from = int(hb["x"] - tb["x"] + hb["width"] + 2)
    gap_x = detect_gap_x(
        Path(track_png).read_bytes(),
        Path(piece_png).read_bytes() if piece_png else None,
        search_from=search_from,
    )
    try:
        track_png.unlink(missing_ok=True)
        if piece_png:
            piece_png.unlink(missing_ok=True)
    except OSError:  # noqa: BLE001
        pass
    if gap_x is None:
        return _error(
            "缺口识别失败（截图对比度不足或结构特殊）：请再试一次或降级有头人工拖拽"
            "（两次失败必须降级，避免风险分累积）",
        )

    handle_left = hb["x"] - tb["x"]
    distance = max(8.0, min(float(gap_x) - handle_left, tb["width"] - hb["width"]))
    moves = human_track(distance, random.Random())
    start_x = hb["x"] + hb["width"] / 2
    start_y = hb["y"] + hb["height"] / 2
    try:
        await _pace()
        await page.mouse.move(start_x, start_y)
        await page.mouse.down()
        # dx 为手柄位移（从拖拽起点累积）→ 鼠标 = 起点 + dx
        for dx, dy, delay in moves:
            await page.mouse.move(start_x + dx, start_y + dy)
            await asyncio.sleep(delay / 1000)
        await page.mouse.up()
    except Exception as exc:  # noqa: BLE001
        try:
            await page.mouse.up()
        except Exception:  # noqa: BLE001
            pass
        return _error(f"拖拽执行失败: {type(exc).__name__}: {str(exc)[:200]}")
    await asyncio.sleep(random.uniform(0.4, 0.8))

    verified: bool | None = None
    if success_text:
        try:
            await page.wait_for_selector(
                f"text={success_text}", state="visible", timeout=6000
            )
            verified = True
        except Exception:  # noqa: BLE001
            verified = False
    result = await _snapshot_payload(session, page)
    if verified is False:
        result["success"] = False
        result["message"] = (
            "滑块拖拽后未检测到成功标记（行为风控识别）：最多再试 1 次，"
            "再失败请降级有头人工拖拽"
        )
        result["slider"] = {"distance": round(distance, 1), "verified": False}
        return result
    result["slider"] = {
        "distance": round(distance, 1),
        "moves": len(moves),
        "verified": verified,
    }
    return result


def _parse_grounding_items(text: str) -> list[tuple[str, float, float]] | None:
    """解析视觉模型回复中的 [{label, x, y}, ...]；无有效数组返回 None。"""
    import json as _json
    import re as _re

    if not text:
        return None
    items: list[tuple[str, float, float]] = []
    for chunk in _re.findall(r"\[[^\[\]]*\]", text):
        try:
            arr = _json.loads(chunk)
        except ValueError:
            continue
        if not isinstance(arr, list):
            continue
        for item in arr:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip()
            if label and "x" in item and "y" in item:
                try:
                    items.append((label, float(item["x"]), float(item["y"])))
                except (TypeError, ValueError):
                    continue
        if items:
            return items  # 取第一个可解析的数组
    return None


def _parse_grounding(text: str, labels: list[str]) -> list[tuple[float, float]] | None:
    """按给定 labels 顺序解析坐标；缺任一目标返回 None（兼容旧调用）。"""
    items = _parse_grounding_items(text)
    if items is None or len(items) < len(labels):
        return None
    points: list[tuple[float, float]] = []
    for label in labels:
        match = next((i for i in items if i[0] == label), None)
        if match is None:
            return None
        points.append((match[1], match[2]))
    return points


async def op_solve_click_captcha(
    session: BrowserSession,
    workspace: Path,
    image_ref: str | None = None,
    selector: str | None = None,
    targets: list[str] | None = None,
    submit_text: str | None = None,
    success_text: str | None = None,
) -> dict[str, Any]:
    """点选验证码自动求解（032 §3 L2.6，实验性）。

    验证码图定位二选一：image_ref（快照元素）或 selector（CSS——geetest 类
    canvas/无障碍盲区容器没有 ref，由配方/提示词给出选择器）。
    元素截图（scale=css，像素=CSS 坐标）→ 视觉模型 grounding：
    - targets 给定 → 在图中按顺序找目标；
    - targets 缺省 → 视觉模型自己读提示文字与目标（目标字常由图片渲染，DOM 无文本）。
    换算页面坐标 → 按顺序 mouse.click → 可选确认按钮。仅 confirmed=true 委派段；
    识别失败返回 points=None 降级人工；模型重试 ≤2 次后降级有头浮窗（L4）。
    """
    if not session.confirmed:
        return risk.refusal_payload(
            "点选验证码自动求解仅允许在 confirmed=true 委派段执行（用户在场授权，"
            "行为风控敏感操作）",
            risk="confirmed",
        )
    labels = [str(t).strip() for t in (targets or []) if str(t).strip()]
    if not selector and not image_ref:
        return _error(
            "需要 selector（CSS 定位验证码容器，geetest 类为 .geetest_widget 内的"
            " canvas/图片）或 image_ref（快照 ref）之一",
            rejected=True,
        )
    if labels and len(labels) > 6:
        return _error("targets 最多 6 个目标", rejected=True)
    page = await session.ensure()
    try:
        if image_ref:
            image_meta = _ref_meta(session, image_ref)
            if image_meta is None:
                return _error(
                    "验证码图片 ref 不存在或已过期，请重新 browser_snapshot；"
                    "无障碍盲区的验证码容器请改用 selector 参数",
                    rejected=True,
                )
            image_loc = page.locator(image_meta["selector"])
        else:
            image_loc = page.locator(str(selector).strip()).first
        if await image_loc.count() == 0:
            return _error(
                "验证码图片元素不在页面：确认 selector 是否正确"
                "（geetest 常见为 .geetest_widget 内的 canvas/img）",
                rejected=True,
            )
        bbox = await image_loc.bounding_box()
        if not bbox:
            return _error("无法获取验证码图片几何信息", rejected=True)
        from ...config import output_dir_for_workspace

        out_dir = output_dir_for_workspace(workspace) / "browser"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%H%M%S")
        png = out_dir / f"click-captcha-{stamp}.png"
        # scale="css"：截图像素与 CSS 像素 1:1，grounding 坐标可直接换算
        await image_loc.screenshot(path=str(png), scale="css")
    except Exception as exc:  # noqa: BLE001
        return _error(f"验证码截图失败: {type(exc).__name__}: {str(exc)[:200]}")

    from PIL import Image

    img_w, img_h = Image.open(png).size
    if labels:
        vision_prompt = (
            "在图中按顺序找到以下目标："
            + "、".join(f"「{label}」" for label in labels)
            + "。返回 JSON 数组，每项形如 {\"label\": \"目标\", \"x\": <中心横坐标像素>, "
            "\"y\": <中心纵坐标像素>}，顺序与给定顺序一致。只输出 JSON，不要其他内容。"
        )
    else:
        vision_prompt = (
            "这是一张点选验证码。第一步：读出图中提示要求依次点击的目标文字；"
            "第二步：返回每个目标中心的坐标。输出 JSON 数组，每项形如 "
            "{\"label\": \"目标文字\", \"x\": <中心横坐标像素>, \"y\": <中心纵坐标像素>}，"
            "按提示要求的点击顺序排列。只输出 JSON，不要其他内容。"
        )
    try:
        code = await _vision_caption(png, prompt=vision_prompt)
    finally:
        try:
            png.unlink(missing_ok=True)
        except OSError:  # noqa: BLE001
            pass

    items = _parse_grounding_items(code or "")
    if items is None or (labels and len(items) < len(labels)):
        return _ok(
            {
                "points": None,
                "message": (
                    "点选目标识别失败（视觉模型未配置、目标文字读不出或 grounding 不准）："
                    "请降级为登录卡片人工点选，不要盲目点击"
                ),
            }
        )
    if labels:
        ordered: list[tuple[str, float, float]] = []
        for label in labels:
            match = next((item for item in items if item[0] == label), None)
            if match is None:
                return _ok(
                    {
                        "points": None,
                        "message": f"目标「{label}」未在图中识别到：请降级为登录卡片人工点选",
                    }
                )
            ordered.append(match)
        resolved_labels = labels
        points = [(ix, iy) for _, ix, iy in ordered]
    else:
        resolved_labels = [item[0] for item in items]
        points = [(ix, iy) for _, ix, iy in items]

    try:
        for label, (ix, iy) in zip(resolved_labels, points):
            px = bbox["x"] + (ix / img_w) * bbox["width"]
            py = bbox["y"] + (iy / img_h) * bbox["height"]
            await _pace()
            await page.mouse.click(px, py)
        if submit_text:
            await _pace()
            submit_loc = page.get_by_text(str(submit_text), exact=False).first
            if await submit_loc.count() > 0:
                await submit_loc.click(timeout=_ACTION_TIMEOUT_MS)
    except Exception as exc:  # noqa: BLE001
        return _error(f"点选执行失败: {type(exc).__name__}: {str(exc)[:200]}")
    await asyncio.sleep(random.uniform(0.4, 0.8))

    verified: bool | None = None
    if success_text:
        try:
            await page.wait_for_selector(
                f"text={success_text}", state="visible", timeout=6000
            )
            verified = True
        except Exception:  # noqa: BLE001
            verified = False
    result = await _snapshot_payload(session, page)
    if verified is False:
        result["success"] = False
        result["message"] = (
            "点选提交后未通过（识别或顺序有误）：最多再试 1 次，"
            "再失败请降级有头人工点选"
        )
        result["click_captcha"] = {"targets": labels, "verified": False}
        return result
    result["click_captcha"] = {"targets": labels, "points": points, "verified": verified}
    return result


async def op_read_page(session: BrowserSession, workspace: Path) -> dict[str, Any]:
    """元素截图 → 视觉模型 caption（031 §4 caption 路径）。

    截图是 caption 的**一次性输入**：存到工作区 `browser/` 子目录，caption
    生成（或降级为可见文本）后立即删除，不在工作区残留文件。
    """
    page = await session.ensure()
    try:
        from ...config import output_dir_for_workspace

        out_dir = output_dir_for_workspace(workspace) / "browser"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"browser-page-{time.strftime('%H%M%S')}-{random.randint(100, 999)}.jpg"  # noqa: S311
        await page.screenshot(
            path=str(path), type="jpeg", quality=70, full_page=False
        )
    except Exception as exc:  # noqa: BLE001
        return _error(f"截图失败: {type(exc).__name__}: {str(exc)[:200]}")

    try:
        caption = await _vision_caption(path, model_id=getattr(session, "model_id", None))
    finally:
        # 用完即删：截图只是视觉描述的输入，不作为工作区产物保留
        try:
            path.unlink(missing_ok=True)
        except OSError:  # noqa: BLE001 — 删除失败不阻塞，文件在 browser/ 里可手动清
            logger.warning("临时截图删除失败: %s", path)

    if caption:
        return _ok({"message": "页面截图（视觉描述）", "caption": caption})

    # 降级：可见文本摘要（快照已含结构，文本只做视觉盲区兜底）
    try:
        visible = await page.evaluate(
            "() => (document.body ? document.body.innerText : '').slice(0, 4000)"
        )
    except Exception:  # noqa: BLE001
        visible = ""
    return _ok(
        {
            "message": "已提取页面可见文本（截图为一次性输入，已删除）",
            "visible_text": visible,
        }
    )


async def _vision_caption(
    image_path: Path, prompt: str | None = None, model_id: str | None = None
) -> str | None:
    """视觉识别级联（032 §3）：GLM（免费）→ 当前会话模型 → 其他已配置多模态。

    任一环节失败（未配置/401/限流）自动降级到下一个，全部失败才返回 None。
    此前单点失败即放弃：mimo key 失效就把 GLM 一起带崩（实测）。
    """
    import base64

    import httpx

    from ...config import settings_store
    from ..scripts.read_image import (
        _is_multimodal_model,
        _resolve_by_model_id,
        _resolve_glm,
        _resolve_multimodal,
    )

    settings = settings_store.load()

    # 级联候选：(api_key, base_url, model) 有序去重
    candidates: list[tuple[str, str, str]] = []

    glm = _resolve_glm(settings)
    if glm is not None:
        candidates.append(glm)

    if model_id:
        entry = _resolve_by_model_id(settings, model_id)
        if (
            entry is not None
            and entry.get("api_key")
            and _is_multimodal_model(str(entry.get("model") or ""))
        ):
            candidates.append(
                (
                    str(entry["api_key"]),
                    str(entry.get("base_url") or ""),
                    str(entry.get("model") or ""),
                )
            )

    extra = _resolve_multimodal(settings)
    if extra is not None and extra[0]:
        candidates.append(extra)

    # 去重（同 key+model 只试一次）；空 base_url 补 GLM 官方端点兜底
    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[str, str, str]] = []
    for api_key, base_url, model in candidates:
        if not api_key or (api_key, model) in seen:
            continue
        seen.add((api_key, model))
        ordered.append((api_key, base_url or "https://open.bigmodel.cn/api/paas/v4", model))

    b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    final_prompt = prompt or (
        "用简洁中文描述这个网页截图：页面主题、主要区块、"
        "可操作元素（按钮/输入框/链接）。120 字以内。"
    )
    for api_key, base_url, model in ordered:
        try:
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
                                {"type": "text", "text": final_prompt},
                            ],
                        }
                    ],
                    "max_tokens": 300,
                },
            )
            response.raise_for_status()
            caption = str(
                response.json()["choices"][0]["message"]["content"] or ""
            ).strip()
            if caption:
                return caption
        except Exception as exc:  # noqa: BLE001 — 级联：单源失败换下一个
            logger.warning(
                "vision caption via %s failed: %s: %s",
                model,
                type(exc).__name__,
                str(exc)[:120],
            )
    return None
