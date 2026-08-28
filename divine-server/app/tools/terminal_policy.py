from __future__ import annotations

import re


_SAFE_TERMINAL_COMMANDS = {
    "ls",
    "pwd",
    "echo",
    "printf",
    "whoami",
    "uname",
    "date",
    "which",
    "type",
    "file",
    "du",
    "df",
    "pytest",
    "python",
    "python3",
    "node",
    "tsc",
    "eslint",
    "mypy",
    "pnpm",
    "npm",
    "yarn",
    "npx",
    "bun",
    "pip",
    "pip3",
    "uv",
    "poetry",
}

# git subcommands that are read-only; anything else (commit/push/reset/...) is
# a write and stays on the confirm path.
_SAFE_GIT_SUBCOMMANDS = {
    "status",
    "diff",
    "log",
    "show",
    "branch",
    "remote",
    "ls-files",
    "rev-parse",
    "stash",
    "tag",
    "blame",
    "grep",
    "help",
    "--version",
}

# 硬拦截：即使询问也不放开（系统/磁盘级破坏，误确认即不可逆）。
# rm -rf / rm -fr 递归删除同样保留硬拦截——需要删目录时请用普通 rm 或
# 在系统终端操作，避免 AI 误触。其余常见开发命令（sudo / kill -9 / chmod
# 777 / find / -name / heredoc / curl / wget 等）不在黑名单里，会落到下面
# 的 confirm 分级，由用户在弹窗里确认后执行——用户授权即可执行，无论内外网。
_BLOCKED_TERMINAL_TOKENS = (
    "rm -rf",
    "rm -fr",
    "shutdown",
    "reboot",
    "diskutil",
    "mkfs",
    "dd if=",
    "> /dev/sd",
    "chown -r",
)

_SHELL_CONTROL_RE = re.compile(r"(?:\|\||&&|;|\||&|`|\$\(|\$\{|\n)")


def _base_command(normalized: str) -> tuple[str, str | None]:
    """Return (first command word, second word) for a normalized command."""
    parts = normalized.split()
    if not parts:
        return "", None
    base = parts[0].rsplit("/", 1)[-1]
    second = parts[1] if len(parts) > 1 else None
    return base, second


def terminal_command_policy(command: str) -> str:
    normalized = command.strip().lstrip("$ ").lower()
    # curl/wget：不硬拦截，一律"确认"——用户授权后即可执行（含外网）
    if re.match(r"^(curl|wget)\b", normalized):
        return "confirm"
    if any(token in normalized for token in _BLOCKED_TERMINAL_TOKENS):
        return "block"
    if _SHELL_CONTROL_RE.search(normalized):
        return "confirm"
    base, second = _base_command(normalized)
    if base == "git":
        # git alone (no subcommand) shows help; still safe.
        if second in _SAFE_GIT_SUBCOMMANDS:
            return "safe"
        return "confirm"
    return "safe" if base in _SAFE_TERMINAL_COMMANDS else "confirm"
