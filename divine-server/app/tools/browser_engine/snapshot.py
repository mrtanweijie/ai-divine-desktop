"""aria 快照 + ref 映射（031 §4）。

约定：
- 元素定位一律基于快照返回的 ref，不裸用 CSS selector；
- ref 通过在 DOM 上打 ``data-divine-ref`` 属性实现，会话内单调递增，
  旧编号永不复用；全页快照会先清掉全部旧标记（旧 ref 自然过期）；
- 快照规模上限：行数与字符数双上限，超限截断并提示改用子树快照/extract；
- SELECT 展开选项、输入框带 value、链接带 href，尽量一个快照让模型"看清"页面。
"""

from __future__ import annotations

from typing import Any

from .session import BrowserSession

SNAPSHOT_MAX_LINES = 4000
SNAPSHOT_MAX_CHARS = 24_000  # ≈ 8k token 量级，超出提示缩小范围
_NAME_CAP = 100
_TEXT_CAP = 120

# 注入页面的快照构建器：返回结构化条目，由 Python 端渲染文本
_SNAPSHOT_JS = r"""
(args) => {
  const { ref, startIndex } = args;
  const rootEl = ref
    ? document.querySelector('[data-divine-ref="' + ref + '"]')
    : document.body;
  if (!rootEl) return { error: "REF_NOT_FOUND" };

  if (!ref) {
    document.querySelectorAll("[data-divine-ref]").forEach((el) => {
      el.removeAttribute("data-divine-ref");
    });
  }

  const INTERACTIVE_TAGS = new Set(["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA", "SUMMARY", "OPTION"]);
  const HEADINGS = new Set(["H1", "H2", "H3", "H4"]);
  const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "SVG", "IFRAME", "LINK", "META", "TEMPLATE", "CANVAS"]);

  function roleOf(el) {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit;
    // contenteditable 富文本编辑器（掘金/飞书等现代编辑器普遍无 role）→ textbox
    const ce = el.getAttribute && el.getAttribute("contenteditable");
    if (ce === "true" || ce === "") return "textbox";
    if (el.isContentEditable) {
      const parentEditable = el.parentElement && el.parentElement.isContentEditable;
      if (!parentEditable) return "textbox";
    }
    const tag = el.tagName;
    if (tag === "INPUT") {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "button" || type === "submit") return "button";
      if (type === "file") return "file";
      return "textbox";
    }
    if (tag === "A") return "link";
    if (tag === "BUTTON" || tag === "SUMMARY") return "button";
    if (tag === "SELECT") return "combobox";
    if (tag === "TEXTAREA") return "textbox";
    if (tag === "OPTION") return "option";
    return null;
  }

  function firstLine(text) {
    return String(text || "")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 3)
      .join(" ");
  }

  function nameOf(el) {
    const label =
      el.getAttribute("aria-label") ||
      el.getAttribute("placeholder") ||
      el.getAttribute("alt") ||
      el.getAttribute("title") ||
      (el.tagName === "INPUT" && el.labels && el.labels[0] ? firstLine(el.labels[0].innerText) : "") ||
      firstLine(el.innerText) ||
      firstLine(el.value) ||
      "";
    return label.slice(0, 100);
  }

  function isHidden(el) {
    if (el.getAttribute && el.getAttribute("aria-hidden") === "true") return true;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return true;
    const rect = el.getBoundingClientRect();
    return rect.width === 0 && rect.height === 0;
  }

  let counter = startIndex || 0;
  const items = [];

  function walk(el, depth) {
    if (items.length >= 4000 || depth > 25) return;
    if (el.nodeType !== 1) return;
    if (SKIP_TAGS.has(el.tagName)) return;
    let style = null;
    let hidden = false;
    try {
      style = window.getComputedStyle(el);
      hidden = style.display === "none" || style.visibility === "hidden";
    } catch (e) { hidden = false; }
    if (hidden) return;
    if (el.getAttribute && el.getAttribute("aria-hidden") === "true") return;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return;

    const tag = el.tagName;
    let role = null;
    try { role = roleOf(el); } catch (e) { role = null; }
    // React/Vue 事件走根节点委托，DOM 上没有 onclick——用 cursor:pointer
    // 兜底识别"可点但无 role"的框架控件（惰性下拉、菜单项等）
    const clickable = el.hasAttribute("onclick")
      || el.getAttribute("tabindex") !== null
      || (style && style.cursor === "pointer");

    if (role || clickable) {
      const name = nameOf(el);
      counter += 1;
      const refId = "e" + counter;
      try { el.setAttribute("data-divine-ref", refId); } catch (e) {}
      const item = { t: "el", role: role || (clickable ? "clickable" : "generic"), name, ref: refId, depth };
      if (tag === "A" && el.getAttribute("href")) {
        item.extra = "href=" + String(el.getAttribute("href")).slice(0, 120);
      }
      if ((tag === "INPUT" || tag === "TEXTAREA") && el.value) {
        item.extra = 'value="' + String(el.value).slice(0, 60) + '"';
      }
      if (tag !== "INPUT" && tag !== "TEXTAREA" && el.isContentEditable) {
        item.extra = (item.extra ? item.extra + " " : "") + "[contenteditable]";
      }
      items.push(item);
      if (tag === "SELECT") {
        const options = Array.from(el.options || []).slice(0, 30);
        for (const opt of options) {
          items.push({
            t: "opt",
            name: String(opt.textContent || "").trim().slice(0, 60),
            selected: !!opt.selected,
            depth: depth + 1,
          });
        }
        return;
      }
    } else if (HEADINGS.has(tag)) {
      const name = firstLine(el.innerText).slice(0, 120);
      if (name) items.push({ t: "hd", name, tag: tag.toLowerCase(), depth });
    } else if (el.children.length === 0) {
      const text = firstLine(el.innerText).slice(0, 120);
      if (text) items.push({ t: "txt", name: text, depth });
    }

    for (const child of Array.from(el.children || [])) {
      walk(child, depth + 1);
    }
  }

  walk(rootEl, 0);
  return {
    url: location.href,
    title: document.title,
    items,
  };
}
"""


def render_lines(items: list[dict[str, Any]]) -> list[str]:
    """把 JS 条目渲染成模型可读的快照文本行。"""
    lines: list[str] = []
    for item in items:
        depth = int(item.get("depth") or 0)
        indent = "  " * depth
        kind = item.get("t")
        name = str(item.get("name") or "").replace('"', "'")
        if kind == "el":
            line = f'{indent}- {item.get("role")}' + (f' "{name}"' if name else "")
            line += f" [ref={item.get('ref')}]"
            if item.get("extra"):
                line += f" {item['extra']}"
        elif kind == "opt":
            line = f'{indent}- option "{name}"' + (" [selected]" if item.get("selected") else "")
        elif kind == "hd":
            line = f'{indent}- heading "{name}" ({item.get("tag")})'
        else:
            line = f'{indent}- text "{name}"'
        lines.append(line[:_TEXT_CAP + 80])
    return lines


async def build_snapshot(
    session: BrowserSession,
    page: Any,
    ref: str | None = None,
    max_chars: int = SNAPSHOT_MAX_CHARS,
) -> dict[str, Any]:
    """构建当前页面（或 ref 子树）快照；同步更新会话 ref 映射。"""
    result = await page.evaluate(_SNAPSHOT_JS, {"ref": ref, "startIndex": session.ref_counter})
    if result.get("error") == "REF_NOT_FOUND":
        return {
            "success": False,
            "message": f"编号 {ref} 不存在或已过期，请重新 browser_snapshot 获取最新页面",
            "rejected": True,
        }
    items = result.get("items") or []
    lines = render_lines(items)
    truncated = False
    if len(lines) > SNAPSHOT_MAX_LINES:
        lines = lines[:SNAPSHOT_MAX_LINES]
        truncated = True

    # 更新 ref 映射：全页快照重置映射；子树快照合并（旧 ref 若元素仍在则仍可用）
    if not ref:
        session.refs.clear()
    for item in items:
        if item.get("t") == "el" and item.get("ref"):
            session.refs[str(item["ref"])] = {
                "selector": f'[data-divine-ref="{item["ref"]}"]',
                "role": str(item.get("role") or ""),
                "name": str(item.get("name") or ""),
            }

    body = "\n".join(lines)
    note = ""
    if truncated or len(body) > max_chars:
        body = body[:max_chars]
        truncated = True
    if truncated:
        note = (
            "\n[快照超长已截断——请用 browser_snapshot(ref) 取子树、"
            "或 browser_extract 做结构化抽取，不要反复全页快照]"
        )

    return {
        "success": True,
        "url": result.get("url") or "",
        "title": result.get("title") or "",
        "snapshot": f'页面: {result.get("title") or ""}\nURL: {result.get("url") or ""}\n' + body + note,
    }
