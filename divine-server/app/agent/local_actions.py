"""本地意图的真实执行（不调云端 LLM）。

由 orchestrator 在检测到本地可处理意图时调用。返回给用户的回复文本；
无法执行（目标不明 / 命令失败 / 缺少权限）时返回 None，调用方回退到
云端 agent —— 绝不吞掉用户消息。

支持的动作：
- open_app：macOS `open` 打开应用（含常见中文名映射）
- screenshot：`screencapture` 截图
- lock_screen：锁定屏幕（CGSession / pmset 兜底）
- search_file：`mdfind` 查找文件
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# 常见应用中文名 → macOS 应用名（`open -a` 需要英文名）
_APP_ALIASES = {
    "计算器": "Calculator",
    "浏览器": "Safari",
    "访达": "Finder",
    "邮件": "Mail",
    "备忘录": "Notes",
    "日历": "Calendar",
    "提醒事项": "Reminders",
    "设置": "System Settings",
    "系统设置": "System Settings",
    "终端": "Terminal",
    "微信": "WeChat",
    "企业微信": "WeCom",
    "钉钉": "DingTalk",
    "chrome": "Google Chrome",
    "谷歌浏览器": "Google Chrome",
    "safari": "Safari",
    "vscode": "Visual Studio Code",
    "代码": "Visual Studio Code",
    "网易云音乐": "NetEase Music",
    "腾讯会议": "TencentMeeting",
    "qq": "QQ",
    "音乐": "Music",
    "照片": "Photos",
    "便笺": "Stickies",
    "word": "Microsoft Word",
    "excel": "Microsoft Excel",
    "ppt": "Microsoft PowerPoint",
}

# 从"帮我打开XXX"里剥掉语气词/动作词，剩下的是目标
_OPEN_STRIP = re.compile(
    r"帮我|请|一下|打开|启动|运行|快|立刻|马上|把|给我|打开文件夹|文件夹|应用|程序|软件"
)

_CGSESSION = (
    "/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession"
)


def _run(
    cmd: list[str], timeout: float = 8.0, use_stderr: bool = True
) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        output = (r.stdout or "")
        if use_stderr:
            output += (r.stderr or "")
        return r.returncode, output.strip()
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def _extract_target(text: str) -> str:
    t = _OPEN_STRIP.sub("", text)
    return t.strip(" \t，。？！?,.!；;：:")


def _open_app(text: str) -> str | None:
    target = _extract_target(text)
    if not target:
        logger.info("open_app 目标为空: %r", text[:50])
        return None
    name = _APP_ALIASES.get(target.lower(), target)
    code, err = _run(["open", "-a", name])
    if code == 0:
        return f"已打开 {target}"
    # 兜底：按路径打开（目录/文件）
    code2, err2 = _run(["open", target])
    if code2 == 0:
        return f"已打开 {target}"
    logger.info(
        "open_app 失败 target=%r: %s / %s",
        target,
        err[:120],
        err2[:120],
    )
    return None


def _screenshot(output_dir: Path) -> str | None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("截图目录创建失败: %s", e)
        return None
    path = output_dir / f"screenshot-{int(time.time())}.png"
    code, err = _run(["screencapture", "-x", str(path)], timeout=15.0)
    if code == 0 and path.exists() and path.stat().st_size > 0:
        return f"已截图保存到 {path}"
    logger.info("screencapture 失败: %s", err[:120])
    return None


def _lock_screen() -> str | None:
    if Path(_CGSESSION).exists():
        code, _ = _run([_CGSESSION, "-suspend"], timeout=8.0)
        if code == 0:
            return "已锁定屏幕"
    code, _ = _run(["pmset", "displaysleepnow"], timeout=8.0)
    if code == 0:
        return "屏幕已休眠（如需完全锁定请手动操作）"
    return None


def _search_files(text: str) -> str | None:
    query = _extract_target(text)
    if not query:
        query = text.strip(" \t，。？！?,.!；;：:")
    if not query:
        return None
    code, out = _run(["mdfind", "-name", query], timeout=15.0, use_stderr=False)
    lines = [line for line in out.splitlines() if line.strip()][:5]
    if code != 0 or not lines:
        code2, out2 = _run(["mdfind", query], timeout=15.0, use_stderr=False)
        lines = [line for line in out2.splitlines() if line.strip()][:5]
    if not lines:
        logger.info("search_file 无结果 query=%r", query[:50])
        return None
    return "找到以下文件：\n" + "\n".join(lines)


def execute_local_action(
    intents: set[str], text: str, output_dir: Path
) -> str | None:
    """执行本地意图；返回回复文本；无法执行返回 None（调用方回退云端）。"""
    for intent in ("open_app", "screenshot", "lock_screen", "search_file"):
        if intent not in intents:
            continue
        try:
            if intent == "open_app":
                result = _open_app(text)
            elif intent == "screenshot":
                result = _screenshot(output_dir)
            elif intent == "lock_screen":
                result = _lock_screen()
            else:
                result = _search_files(text)
            if result:
                return result
        except Exception as e:  # noqa: BLE001
            logger.warning("本地动作 %s 异常: %s", intent, e)
    return None
