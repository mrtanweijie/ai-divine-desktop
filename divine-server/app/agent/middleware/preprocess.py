"""输入侧本地预整理：长文本先由本地小模型整理成结构化版本，再交给云端。

数据流与规则见 docs/design/005-preprocess-20260829.md。

- 触发：显式（指令词 + 文本指代词双命中）或自动（token 估算 > 阈值，且非
  代码/表格/指针文本，且本地模型可用）。
- 降级：本地模型不可用或整理失败 → 原样上云，绝不吞消息、不阻塞对话。
- 附件：原文写入 ``workspace/sessions/{sid}/attachments/original-{ts}.md``，
  云端通过 read_file 按需读取（不注入模型上下文，省 token）。
"""

from __future__ import annotations

import difflib
import logging
import re
import time
from pathlib import Path

from ..intent import _ABS_PATH_RE, _looks_like_abs_path, strip_abs_paths

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 显式触发：指令词 + 文本指代词 双命中（决策 1，防"帮我整理房间"误触发）
# ---------------------------------------------------------------------------

_ORGANIZE_VERBS = (
    "整理",
    "梳理",
    "归纳",
    "总结",
    "帮我理一下",
    "理一下",
    "organize",
    "structure",
    "summarize",
)
_ORGANIZE_REFERRERS = (
    "这段",
    "这个",
    "以下内容",
    "下面内容",
    "下面的话",
    "上面的话",
    "上面的文字",
    "上面内容",
    "这段文字",
    "这篇文章",
    "这段内容",
    "以下文字",
    "如下内容",
    "这份",
    "这个文档",
    "这段文本",
    "这段笔记",
    "这份材料",
    "这段记录",
)

# 指针：URL
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)

# 分块参数（现有 llama-server 默认 ctx 4096，塞不下超长输入）
_CHUNK_CHARS = 2000  # 单块字符上限
_MAX_CHUNKS = 5  # 分块上限（>10k 字只整理前 5 块，其余进附件）

# 原文附件目录名（会话工作区下，与截图 screenshots/ 同风格）
_ATTACHMENT_DIR = "attachments"
_ATTACHMENT_PREFIX = "original-"


def _strip_pointers(text: str) -> str:
    """去掉文本中的 URL 与本地绝对路径（严格判定），返回剩余部分。"""
    t = strip_abs_paths(text)
    t = _URL_RE.sub(" ", t)
    return t.strip(" \t\n，。；、！？?,.!；;：:()（）\"'")


def _is_pointer_only(text: str) -> bool:
    """消息"基本就是"链接 / 本地路径 → 跳过整理，原样上云。

    两种形态都算：
    1. 去掉指针后剩余为空或极短（纯路径/纯 URL 消息）；
    2. 消息很短但带指针（如"帮我整理这个链接 https://…"）——指针就是
       待处理的内容，本地模型只会把 URL 当字符串复述，交给云端
       read_file / web_fetch 处理（"路径+整理指令"留 v2）。
    """
    rest = _strip_pointers(text)
    if len(rest) <= 2:
        return True
    has_pointer = bool(_URL_RE.search(text)) or any(
        _looks_like_abs_path(p) for p in _ABS_PATH_RE.findall(text)
    )
    return has_pointer and len(text) < 120


def _is_explicit(text: str, has_referent_attachment: bool = False) -> bool:
    """显式触发：指令词 + 文本指代词 双命中。

    ``has_referent_attachment=True`` 时附件即指代对象——"帮我整理" + 附件
    是明确的整理请求（附件就是要整理的内容），无需再匹配"这段/这个"。
    """
    if not any(v in text for v in _ORGANIZE_VERBS):
        return False
    if has_referent_attachment:
        return True
    return any(r in text for r in _ORGANIZE_REFERRERS)


def _looks_like_code(text: str) -> bool:
    """代码特征检测：围栏 / 高缩进密度 / 分号结尾占比。"""
    if "```" in text or "~~~" in text:
        return True
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    indented = sum(1 for line in lines if re.match(r"^\s{2,}", line))
    if indented / len(lines) > 0.5:
        return True
    semicolon = sum(
        1 for line in lines if line.rstrip().endswith((";", "{", "}"))
    )
    return semicolon / len(lines) > 0.3


def _looks_like_table(text: str) -> bool:
    """表格/CSV 特征检测：多行使用同一分隔符且列结构一致。"""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    # Markdown 表格 / TSV：竖线或制表符
    for delim in ("|", "\t"):
        hits = sum(
            1 for line in lines if (line.count("|") >= 2 if delim == "|" else delim in line)
        )
        if hits >= max(2, len(lines) // 2):
            return True
    # CSV：逗号数一致的行占比高
    counts = [line.count(",") for line in lines]
    if max(counts) >= 2 and max(counts) - min(counts) <= 1:
        consistent = sum(1 for c in counts if c == max(counts))
        if consistent >= max(2, len(lines) // 2):
            return True
    return False


def _token_estimate(text: str) -> int:
    from ..state import estimate_tokens

    return estimate_tokens(text)


def _chunks(text: str) -> list[str]:
    """按段落切块，单块 ≤ _CHUNK_CHARS（优先在空行/句号处断开）。"""
    if len(text) <= _CHUNK_CHARS:
        return [text]
    chunks: list[str] = []
    rest = text
    while len(rest) > _CHUNK_CHARS and len(chunks) < _MAX_CHUNKS - 1:
        cut = _CHUNK_CHARS
        head = rest[:cut]
        for sep in ("\n\n", "\n", "。", "；", " "):
            idx = head.rfind(sep)
            if idx > cut // 2:
                cut = idx + len(sep)
                break
        chunks.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        chunks.append(rest)
    return chunks


def _latest_original(workspace: Path, session_id: str) -> Path | None:
    """最近一次预整理的原文附件路径（多轮退化检测用）。"""
    att_dir = workspace / "sessions" / session_id / _ATTACHMENT_DIR
    if not att_dir.is_dir():
        return None
    files = sorted(
        att_dir.glob(f"{_ATTACHMENT_PREFIX}*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def maybe_preprocess(
    text: str,
    session_id: str,
    workspace: Path,
) -> tuple[str, Path | None, bool, bool]:
    """长文本本地预整理。

    返回 (最终消息文本, 原文附件路径或 None, 是否已整理, 是否尝试过整理)。
    - 未触发 / 降级：返回 (原文本, None, False, False)，调用方原样上云。
    - 已整理：返回 (核对提示 + 整理版, 附件路径, True, True)。
    - 触发但失败：返回 (原文本, None, False, True)——调用方可据此询问用户
      是否仍走云端（见 chat.py 的 preprocess_fallback 确认流）。
    """
    if not text or not text.strip():
        return text, None, False, False

    from ...config import settings_store

    settings = settings_store.load()
    if not settings.get("local_llm_preprocess_enabled", True):
        return text, None, False, False

    # 指针消息（URL / 本地路径）：跳过整理，云端 read_file / web_fetch
    if _is_pointer_only(text):
        return text, None, False, False

    explicit = _is_explicit(text)
    if not explicit:
        if not settings.get("local_llm_preprocess_auto", True):
            return text, None, False, False
        if _token_estimate(text) < int(
            settings.get("local_llm_preprocess_threshold", 800)
        ):
            return text, None, False, False
        if settings.get("local_llm_preprocess_code_skip", True) and _looks_like_code(
            text
        ):
            return text, None, False, False
        if _looks_like_table(text):
            return text, None, False, False
    else:
        # 多轮退化：输入与最近一次原文几乎相同 → 不重复整理（P1）
        latest = _latest_original(workspace, session_id)
        if latest is not None:
            try:
                prev = latest.read_text(encoding="utf-8", errors="replace")
                if difflib.SequenceMatcher(None, text, prev).ratio() > 0.8:
                    return text, None, False, False
            except OSError:
                pass

    organized_text, original_path = _organize_text(text, session_id, workspace)
    if not organized_text or original_path is None:
        return text, None, False, True

    # 核对提示前缀：防整理错带偏云端（质量保险）
    final_text = (
        "（用户原文已保存为工作区附件，整理版可能有遗漏，"
        "关键信息请读附件核对）\n\n" + organized_text
    )
    return final_text, original_path, True, True


def _start_local_model(manager) -> bool:
    """预整理需要本地模型但 llama-server 没在跑时，自动拉起（冷启动 10-40s）。

    选模型顺序：设置里的 local_llm_model → 已装模型里优先 1.5B → 第一个已装模型。
    返回是否就绪；无模型/启动失败/超时返回 False（调用方降级云端）。
    注：App 的 sidecar 重启会杀掉孤儿 llama-server（_free_orphan_port），
    模型"起得来留不住"，自动拉起是让预整理不依赖模型常驻的关键。
    """
    try:
        status = manager.get_status()
        installed = status.get("installed_models") or []
        if not installed:
            logger.info("本地预整理需要模型，但未安装任何模型，降级云端")
            return False

        from ...config import settings_store

        preferred = settings_store.load().get("local_llm_model") or ""
        model = None
        for entry in installed:
            if preferred and (
                entry.get("id") == preferred
                or entry.get("registry_id") == preferred
            ):
                model = entry
                break
        if model is None:
            model = next(
                (
                    entry
                    for entry in installed
                    if "1.5b" in str(entry.get("id") or "").lower()
                ),
                None,
            )
        if model is None:
            model = installed[0]
        model_id = model.get("id") or model.get("registry_id")
        path = model.get("path")
        if not model_id or not path:
            logger.warning("本地模型条目缺少 id/path，无法自动拉起")
            return False

        logger.info("本地预整理自动拉起模型: %s (%s)", model_id, path)
        ok, err = manager.start(model_id, path, wait_s=10.0)
        deadline = time.time() + 40.0
        while time.time() < deadline:
            if manager.is_ready():
                logger.info("本地模型自动拉起成功: %s", model_id)
                return True
            # start 快速失败（二进制/模型缺失）→ 不再等待
            if not ok and getattr(manager, "process", None) is None:
                logger.warning("本地模型启动失败，降级云端: %s", err)
                return False
            time.sleep(2)
        logger.warning("本地模型自动拉起超时（40s），降级云端")
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("本地模型自动拉起异常，降级云端: %s", e)
        return False


def _organize_text(
    text: str,
    session_id: str,
    workspace: Path,
    write_original: bool = True,
) -> tuple[str | None, Path | None]:
    """分块调用本地模型整理文本。

    返回 (整理文本, 原文附件路径)；模型不可用/整理失败/附件写入失败返回
    (None, None)。``write_original=False`` 时不写新附件（附件自身即原文，
    如 paste-*.txt），由调用方传回附件路径。
    """
    from ..core.local_llm import get_manager

    manager = get_manager()
    if not manager.is_ready():
        # 自动拉起：预整理不依赖模型常驻（App sidecar 重启会杀孤儿 llama）
        if not _start_local_model(manager):
            return None, None

    # 分块整理：单块失败不再整体放弃——成功块照常整理，失败块原样保留并
    # 标注（部分成功）。全部失败才返回 None（调用方询问用户/原样上云）。
    parts = _chunks(text)[:_MAX_CHUNKS]
    results: list[str] = []
    failed: list[int] = []
    for index, part in enumerate(parts, 1):
        organized = manager.organize(part, timeout=30.0)
        if not organized:
            # 重试一次：拒绝（无法整理）/ 截断偶尔是采样噪声
            organized = manager.organize(part, timeout=30.0)
        if not organized:
            failed.append(index)
            logger.info(
                "本地整理失败（第 %d/%d 块），该块原样保留", index, len(parts)
            )
            continue
        if len(parts) > 1:
            if organized.startswith("[本地整理版]"):
                organized = (
                    f"[本地整理版（第 {index}/{len(parts)} 部分）]\n"
                    + organized.split("\n", 1)[-1]
                )
            else:
                # 无前缀标记（### 开头）时前置分块标注，保留原标题
                organized = (
                    f"[本地整理版（第 {index}/{len(parts)} 部分）]\n{organized}"
                )
        results.append(organized)

    if not results:
        logger.info("所有分块整理均失败，原样上云")
        return None, None

    organized_text = "\n\n".join(results)
    if failed:
        failed_desc = "、".join(f"第 {i} 块" for i in failed)
        organized_text += (
            f"\n\n（{failed_desc}未能本地整理，原文见附件）"
        )
    if len(text) > _CHUNK_CHARS * _MAX_CHUNKS:
        organized_text += "\n\n（更早内容见原文附件）"

    original_path: Path | None = None
    if write_original:
        # 原文附件落盘（云端 read_file 按需读取，不注入上下文）
        try:
            att_dir = workspace / "sessions" / session_id / _ATTACHMENT_DIR
            att_dir.mkdir(parents=True, exist_ok=True)
            original_path = (
                att_dir / f"{_ATTACHMENT_PREFIX}{int(time.time())}.md"
            )
            original_path.write_text(text, encoding="utf-8")
        except OSError as e:  # noqa: BLE001
            logger.warning("原文附件写入失败: %s", e)
            return None, None
    return organized_text, original_path


def maybe_preprocess_attachment(
    question: str,
    content: str,
    session_id: str,
    workspace: Path,
    original_path: str | None = None,
) -> tuple[str, str | None, bool]:
    """对纯文本附件内容做本地预整理（大段粘贴文本走附件通道时）。

    返回 (处理后的内容, 原文路径, 是否已整理, 是否尝试过整理)。
    - 已整理：内容 = 核对提示 + 整理版；原文路径 = 附件自身路径（传入了
      ``original_path``）或新写的 ``original-*.md``（调用方加入 approved_paths）。
    - 未触发：内容原样，路径 None，attempted=False。
    - 触发但失败：内容原样，路径 None，attempted=True（调用方据此询问用户）。

    触发规则（见 docs/design/005-preprocess-20260829.md §8 附件通道）：
    - 显式：question 含整理指令词（附件即指代对象，无需"这段/这个"）；
    - 自动：内容 token 估算 > 阈值且非代码、非表格。
    """
    if not content or not content.strip():
        return content, None, False, False

    from ...config import settings_store

    settings = settings_store.load()
    if not settings.get("local_llm_preprocess_enabled", True):
        return content, None, False, False

    explicit = _is_explicit(question, has_referent_attachment=True)
    if not explicit:
        if not settings.get("local_llm_preprocess_auto", True):
            return content, None, False, False
        if _token_estimate(content) < int(
            settings.get("local_llm_preprocess_threshold", 800)
        ):
            return content, None, False, False
        if settings.get("local_llm_preprocess_code_skip", True) and _looks_like_code(
            content
        ):
            return content, None, False, False
        if _looks_like_table(content):
            return content, None, False, False

    organized_text, written_path = _organize_text(
        content,
        session_id,
        workspace,
        write_original=(original_path is None),
    )
    if not organized_text:
        return content, None, False, True
    orig = original_path or (str(written_path) if written_path else None)
    if orig is None:
        return content, None, False, True
    final = (
        "（用户原文已保存为附件，整理版可能有遗漏，关键信息请读附件核对）\n\n"
        + organized_text
    )
    return final, orig, True, True
