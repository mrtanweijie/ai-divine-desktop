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

_BLOCKED_TERMINAL_TOKENS = (
    "rm -rf",
    "rm -fr",
    "sudo",
    "kill -9",
    "shutdown",
    "reboot",
    "diskutil",
    "mkfs",
    "dd if=",
    "> /dev/sd",
    "chmod 777",
    "chown -r /",
    "curl ",
    "wget ",
    "find / -name",
    "openpyxl",
    "python3 <<",
    "python <<",
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
