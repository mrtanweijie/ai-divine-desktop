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
)

_SHELL_CONTROL_RE = re.compile(r"(?:\|\||&&|;|\||&|`|\$\(|\$\{|\n)")


def terminal_command_policy(command: str) -> str:
    normalized = command.strip().lstrip("$ ").lower()
    if any(token in normalized for token in _BLOCKED_TERMINAL_TOKENS):
        return "block"
    if _SHELL_CONTROL_RE.search(normalized):
        return "confirm"
    first = normalized.split(maxsplit=1)[0] if normalized else ""
    base = first.rsplit("/", 1)[-1] if first else ""
    return "safe" if base in _SAFE_TERMINAL_COMMANDS else "confirm"
