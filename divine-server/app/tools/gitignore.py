"""Shared .gitignore handling for workspace file tools.

Implements a small, dependency-free approximation of gitignore semantics:
- fnmatch-style patterns; patterns without '/' match any path component,
  patterns with '/' are relative to the .gitignore's directory
- '**' crosses directory separators
- trailing '/' marks directory-only rules
- '!' negation (last matching rule wins within one .gitignore file)

Used by the grep_files / directory_tree scripts and by the agent prompt's
project-skeleton injection. Loaded both in-process and inside tool
subprocesses, so it must stay self-contained.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

# Directories always skipped regardless of .gitignore (perf + noise).
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".svn",
        ".hg",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".cache",
        ".next",
        ".nuxt",
        ".turbo",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "target",
        "bin",
        "obj",
        "out",
        "coverage",
        ".coverage",
        ".DS_Store",
    }
)


class GitignoreMatcher:
    """Rules parsed from a single .gitignore file (paths relative to its dir)."""

    def __init__(self) -> None:
        self._rules: list[tuple[str, bool, bool]] = []  # (glob, negate, dir_only)

    def add_gitignore(self, text: str) -> None:
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negate = line.startswith("!")
            if negate:
                line = line[1:].lstrip()
            dir_only = line.endswith("/")
            if dir_only:
                line = line.rstrip("/")
            if not line:
                continue
            self._rules.append((line, negate, dir_only))

    def ignored(self, rel: str, is_dir: bool) -> bool:
        """True when rel (posix, relative to this matcher's root) is ignored.
        Last matching rule wins; negation re-includes."""
        ignored = False
        for pattern, negate, dir_only in self._rules:
            if dir_only and not is_dir:
                continue
            if _match_glob(pattern, rel):
                ignored = not negate
        return ignored


def _match_glob(pattern: str, rel: str) -> bool:
    if "**" in pattern:
        return _glob_to_regex(pattern).search(rel) is not None
    if "/" in pattern:
        return fnmatch.fnmatch(rel, pattern)
    # No slash: match against any single path component.
    return any(fnmatch.fnmatch(part, pattern) for part in rel.split("/"))


def _glob_to_regex(glob_pattern: str) -> re.Pattern:
    parts: list[str] = []
    i = 0
    n = len(glob_pattern)
    while i < n:
        ch = glob_pattern[i]
        if ch == "*":
            if i + 1 < n and glob_pattern[i + 1] == "*":
                parts.append(".*")
                i += 2
                if i < n and glob_pattern[i] == "/":
                    i += 1
                continue
            parts.append("[^/]*")
        elif ch == "?":
            parts.append("[^/]")
        elif ch == "[":
            j = i + 1
            if j < n and glob_pattern[j] in ("!", "^"):
                j += 1
            if j < n and glob_pattern[j] == "]":
                j += 1
            while j < n and glob_pattern[j] != "]":
                j += 1
            if j >= n:
                parts.append(re.escape(ch))
            else:
                inner = glob_pattern[i + 1 : j]
                if inner.startswith("!"):
                    inner = "^" + inner[1:]
                parts.append("[" + inner + "]")
                i = j
        else:
            parts.append(re.escape(ch))
        i += 1
    return re.compile("".join(parts))


def load_gitignore_rules(
    workspace: Path, base: Path
) -> tuple[list[GitignoreMatcher], list[Path]]:
    """Load .gitignore rules from workspace root down to base.

    Returns (matchers, dirs) aligned pairwise; matchers[i] applies to paths
    relative to dirs[i]. Only ancestor-or-equal directories of base are
    included, so paths below base are covered by every matcher.
    """
    workspace = workspace.resolve()
    base = base.resolve()
    matchers: list[GitignoreMatcher] = []
    dirs: list[Path] = []
    chain: list[Path] = []
    current = base
    while True:
        chain.append(current)
        if current == workspace:
            break
        if workspace in current.parents:
            current = current.parent
        else:
            break
    for directory in reversed(chain):
        matcher = GitignoreMatcher()
        gitignore = directory / ".gitignore"
        try:
            if gitignore.is_file():
                matcher.add_gitignore(
                    gitignore.read_text(encoding="utf-8", errors="replace")
                )
        except OSError:
            pass
        matchers.append(matcher)
        dirs.append(directory)
    return matchers, dirs


def is_ignored(
    matchers: list[GitignoreMatcher],
    dirs: list[Path],
    base: Path,
    rel: str,
    is_dir: bool,
) -> bool:
    """True when the path rel (relative to base) is ignored by any matcher."""
    for matcher, directory in zip(matchers, dirs):
        full = base / rel
        try:
            candidate = full.relative_to(directory).as_posix()
        except ValueError:
            continue
        if matcher.ignored(candidate, is_dir):
            return True
    return False
