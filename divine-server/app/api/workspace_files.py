"""工作区引用候选（`@文件` / 后续的 `/技能`）。

提供 `GET /api/workspace/mentions`，供聊天输入框的候选浮层使用：

- 范围：会话生效工作区（`session_workspace` → 项目目录 → 全局 `workspace_dir()` 回退）；
- 索引：进程内目录索引 + TTL 缓存，避免每次按键都全量扫盘；
- 过滤：隐藏项、版本库/依赖目录、`.gitignore` 规则、超大与归档文件；
- 匹配：前缀优先 → 名称子串 → 路径子串 → 子序列兜底；
- 边界：所有路径解析后必须落在工作区内（`ensure_within`）。

技能候选（`kinds=skill`）复用 `skill_registry` 的**无副作用扫描**，按会话工作区
扫描并独立缓存：候选集合与 agent 侧一致，但不会覆盖 agent 正在使用的单例状态。

另提供 `GET /api/workspace/skill-names`：同一份扫描结果，但返回**不截断**的名称全集，
供消息气泡判断 `/xxx` 是否为真技能（候选接口有 `SKILL_LIMIT` 上限，不能当全集用）。
"""

from __future__ import annotations

import fnmatch
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from .. import db
from ..config import workspace_dir
from ..skills import skill_registry

logger = logging.getLogger(__name__)

try:  # pypinyin 为可选增强依赖（与 db/fts.py 同款）：缺失时拼音匹配自动降级
    from pypinyin import Style, lazy_pinyin

    _PINYIN_AVAILABLE = True
except ImportError:  # pragma: no cover
    Style = None  # type: ignore[assignment]
    lazy_pinyin = None  # type: ignore[assignment]
    _PINYIN_AVAILABLE = False

router = APIRouter(prefix="/workspace", tags=["workspace"])

# 单次扫描的条目上限：超出后停止下钻并标记 truncated
MAX_INDEX_ENTRIES = 50_000
# 超过该体积的文件不进入候选（避免把大文件塞进上下文）
MAX_ENTRY_BYTES = 10 * 1024 * 1024
# 索引缓存存活时间（秒）：TTL 到期重新扫描，兼顾 fs 变更与扫描开销
INDEX_TTL_SECONDS = 30.0
# 缓存的工作区数量上限，超出后清理最旧的一批
MAX_CACHED_WORKSPACES = 32
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_QUERY_LEN = 200
# 技能候选上限：独立于文件 limit（技能总量小，超出部分靠继续输入收敛）
SKILL_LIMIT = 8
# 技能清单缓存存活时间（秒）：安装/卸载后最多滞后这么久可见
SKILL_TTL_SECONDS = 5.0
MAX_CACHED_SKILL_ROOTS = 32
# 分节权重：知识技能在前、能力（含 mcp）在后，与弹层分节顺序一致
SKILL_TYPE_WEIGHT = {"knowledge": 0, "executable": 1, "mcp": 1}
# 同名技能跨来源时的展示优先级：项目 > 用户 > 内置
SKILL_SOURCE_WEIGHT = {"project": 0, "user": 1, "builtin": 2}

# 始终跳过的目录名（版本库、依赖、缓存、构建产物）
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".next",
        ".turbo",
        "node_modules",
        "__pycache__",
        "venv",
    }
)

# 兜底：这些后缀即便体积未超限也不作为文本候选
SKIP_SUFFIXES = frozenset(
    {
        ".7z",
        ".avi",
        ".dll",
        ".dylib",
        ".exe",
        ".gz",
        ".iso",
        ".mkv",
        ".mov",
        ".mp4",
        ".pyc",
        ".pyo",
        ".rar",
        ".so",
        ".tar",
        ".tgz",
        ".zip",
    }
)


@dataclass
class FileEntry:
    """索引中的单个条目（路径均相对工作区，使用 POSIX 分隔符）。"""

    path: str
    is_dir: bool
    size: int
    mtime: float


@dataclass
class DirIndex:
    """某个工作区的目录索引快照。"""

    root: Path
    built_at: float
    root_mtime_ns: int | None
    entries: list[FileEntry] = field(default_factory=list)
    truncated: bool = False


_index_lock = threading.RLock()
_index_cache: dict[str, DirIndex] = {}


def resolve_workspace(session_id: str | None) -> Path | None:
    """解析会话生效工作区；目录不存在时回退全局工作区，仍不可用则返回 None。"""
    if session_id:
        try:
            raw = db.session_workspace(session_id)
        except Exception:
            logger.exception("解析会话工作区失败：session=%s", session_id)
            raw = None
        if raw:
            candidate = Path(raw).expanduser()
            if candidate.is_dir():
                return candidate.resolve()
    fallback = workspace_dir()
    return fallback.resolve() if fallback.is_dir() else None


def ensure_within(root: Path, raw_path: str) -> Path | None:
    """把用户给出的相对路径解析为工作区内路径；越界或不存在时返回 None。

    供后续 mentions 校验与文件读取复用，是路径越界的唯一判定入口。
    """
    if not raw_path.strip():
        return None
    try:
        resolved = (root / raw_path).expanduser().resolve()
    except OSError:
        return None
    if resolved != root and root not in resolved.parents:
        return None
    return resolved


def _load_gitignore_patterns(root: Path) -> list[str]:
    """读取工作区根的 .gitignore（简化解析）。

    只支持最常见写法：跳过空行与注释；忽略 `!` 反选规则（宁可少过滤也不误伤）；
    目录规则去掉结尾 `/` 后按文件名/路径两种模式匹配。
    """
    path = root / ".gitignore"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    patterns: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        patterns.append(line.rstrip("/"))
    return patterns


def _ignored(rel_path: str, name: str, patterns: list[str]) -> bool:
    """按 .gitignore 规则判断是否忽略（简化版，仅用于候选过滤）。"""
    for pattern in patterns:
        if "/" in pattern:
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(
                rel_path, f"{pattern}/*"
            ):
                return True
            continue
        if (
            fnmatch.fnmatch(name, pattern)
            or fnmatch.fnmatch(rel_path, f"*/{pattern}")
            or fnmatch.fnmatch(rel_path, f"*/{pattern}/*")
        ):
            return True
    return False


def _scan(root: Path) -> DirIndex:
    """深度优先扫描工作区，生成索引快照。"""
    patterns = _load_gitignore_patterns(root)
    entries: list[FileEntry] = []
    truncated = False
    pending: list[tuple[str, Path]] = [("", root)]

    while pending and not truncated:
        prefix, directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                children = sorted(iterator, key=lambda item: item.name.lower())
        except OSError:
            continue

        subdirs: list[tuple[str, Path]] = []
        for child in children:
            name = child.name
            if name.startswith("."):
                continue
            if child.is_symlink():
                # 符号链接可能是目录环，直接跳过
                continue
            rel_path = f"{prefix}{name}"
            try:
                is_dir = child.is_dir(follow_symlinks=False)
            except OSError:
                continue

            if is_dir:
                if name in SKIP_DIR_NAMES or _ignored(rel_path, name, patterns):
                    continue
                entries.append(FileEntry(rel_path, True, 0, 0.0))
                subdirs.append((f"{rel_path}/", directory / name))
            else:
                if _ignored(rel_path, name, patterns):
                    continue
                if Path(name).suffix.lower() in SKIP_SUFFIXES:
                    continue
                try:
                    stat = child.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.st_size > MAX_ENTRY_BYTES:
                    continue
                entries.append(
                    FileEntry(rel_path, False, int(stat.st_size), float(stat.st_mtime))
                )

            if len(entries) >= MAX_INDEX_ENTRIES:
                truncated = True
                logger.info("工作区索引超过 %s 条，已截断：%s", MAX_INDEX_ENTRIES, root)
                break

        if not truncated:
            pending.extend(reversed(subdirs))

    entries.sort(key=lambda item: (item.path.count("/"), item.path.lower()))
    try:
        root_mtime_ns = root.stat().st_mtime_ns
    except OSError:
        root_mtime_ns = None
    return DirIndex(
        root=root,
        built_at=time.monotonic(),
        root_mtime_ns=root_mtime_ns,
        entries=entries,
        truncated=truncated,
    )


def _get_index(root: Path) -> DirIndex:
    """取索引快照，命中 TTL 缓存则直接复用。"""
    key = str(root)
    with _index_lock:
        cached = _index_cache.get(key)
    if cached is not None and (time.monotonic() - cached.built_at) < INDEX_TTL_SECONDS:
        return cached

    index = _scan(root)
    with _index_lock:
        _index_cache[key] = index
        if len(_index_cache) > MAX_CACHED_WORKSPACES:
            stale = sorted(_index_cache.items(), key=lambda item: item[1].built_at)
            for stale_key, _ in stale[: MAX_CACHED_WORKSPACES // 4]:
                _index_cache.pop(stale_key, None)
    return index


def _subsequence(needle: str, haystack: str) -> bool:
    """needle 是否为 haystack 的子序列（用于 `cmpts` 命中 `components` 这类缩写）。"""
    position = 0
    for char in haystack:
        if char == needle[position]:
            position += 1
            if position == len(needle):
                return True
    return False


def _score(entry: FileEntry, needle: str) -> int | None:
    """匹配打分，越小越靠前；None 表示不匹配。空查询返回 0（全部参与默认排序）。"""
    if not needle:
        return 0
    path = entry.path.lower()
    name = path.rsplit("/", 1)[-1]
    if name == needle:
        return 0
    if name.startswith(needle):
        return 1
    if needle in name:
        return 2
    if needle in path:
        return 3
    if _subsequence(needle, path):
        return 4
    return None


def _sort_key(entry: FileEntry, score: int) -> tuple[int, int, int, float, str]:
    """同分时：浅层优先 → 路径短优先 → 修改时间新优先 → 字典序稳定。"""
    return (
        score,
        entry.path.count("/"),
        len(entry.path),
        -entry.mtime,
        entry.path.lower(),
    )


def _serialize(entry: FileEntry) -> dict[str, Any]:
    return {
        "kind": "file",
        "path": entry.path,
        "type": "dir" if entry.is_dir else "file",
        "size": entry.size,
        "mtime": int(entry.mtime),
    }


@dataclass
class SkillEntry:
    """技能候选条目：只留展示字段，不缓存 SKILL.md 正文。"""

    name: str
    description: str
    type: str
    source: str
    version: str
    # 拼音首字母索引：让 `/bj` 也能命中「笔记整理」
    name_initials: str = ""
    description_initials: str = ""


_skill_cache: dict[str, tuple[float, list[SkillEntry]]] = {}


def _initials(text: str) -> str:
    """取文本的拼音首字母串（「笔记整理」→ bjzl）。

    纯 ASCII 文本直接返回空串：英文名用普通的子串匹配即可，不必过一遍拼音表。
    """
    if not _PINYIN_AVAILABLE or not text or text.isascii():
        return ""
    try:
        return "".join(
            piece[0] for piece in lazy_pinyin(text, style=Style.FIRST_LETTER) if piece
        ).lower()
    except Exception:  # noqa: BLE001 - 拼音只是增强，失败就当没有
        return ""


def _scan_skills(root: Path) -> list[SkillEntry]:
    """按工作区根目录扫描技能清单（无副作用）。"""
    try:
        metas = skill_registry.scan(project_root=root)
    except Exception:  # noqa: BLE001 - 扫描失败不应拖垮候选接口
        logger.exception("扫描技能候选失败：root=%s", root)
        return []
    return [
        SkillEntry(
            name=meta.name,
            description=meta.description,
            type=meta.type,
            source=meta.source,
            version=meta.version,
            name_initials=_initials(meta.name),
            description_initials=_initials(meta.description),
        )
        for meta in metas.values()
    ]


def _get_skills(root: Path) -> list[SkillEntry]:
    """技能清单的短 TTL 缓存：避免每次按键都重读全部 SKILL.md。"""
    key = str(root)
    now = time.monotonic()
    with _index_lock:
        cached = _skill_cache.get(key)
        if cached is not None and now - cached[0] < SKILL_TTL_SECONDS:
            return cached[1]
    entries = _scan_skills(root)
    with _index_lock:
        _skill_cache[key] = (now, entries)
        if len(_skill_cache) > MAX_CACHED_SKILL_ROOTS:
            stale = sorted(_skill_cache.items(), key=lambda item: item[1][0])
            for stale_key, _ in stale[: len(_skill_cache) - MAX_CACHED_SKILL_ROOTS]:
                _skill_cache.pop(stale_key, None)
    return entries


def _score_skill(entry: SkillEntry, needle: str) -> int | None:
    """技能匹配分级（越靠前越优）：

    名称精确 > 名称前缀 > 名称子串 > 名称拼音 > 描述子串 > 描述拼音 > 子序列。
    """
    if not needle:
        return 0
    name = entry.name.lower()
    if name == needle:
        return 0
    if name.startswith(needle):
        return 1
    if needle in name:
        return 2
    if entry.name_initials and entry.name_initials.startswith(needle):
        return 3
    if needle in entry.description.lower():
        return 4
    if entry.description_initials and entry.description_initials.startswith(needle):
        return 5
    if _subsequence(needle, name):
        return 6
    return None


def _skill_sort_key(entry: SkillEntry, score: int) -> tuple[int, int, int, int, str]:
    """分节顺序优先，其次匹配度、来源、名称长度与字典序（结果稳定）。"""
    return (
        SKILL_TYPE_WEIGHT.get(entry.type, 2),
        score,
        SKILL_SOURCE_WEIGHT.get(entry.source, 3),
        len(entry.name),
        entry.name.lower(),
    )


def _serialize_skill(entry: SkillEntry) -> dict[str, Any]:
    return {
        "kind": "skill",
        # path 与文件条目同义：前端统一取 path 作为插入文本（技能即名称）
        "path": entry.name,
        "name": entry.name,
        "type": entry.type,
        "source": entry.source,
        "description": entry.description,
        "version": entry.version,
    }


@router.get("/mentions")
def list_mentions(
    q: str | None = Query(None, max_length=MAX_QUERY_LEN),
    session_id: str | None = Query(None),
    kinds: str = Query("file"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """返回 `@` / `/` 候选条目，支持 `kinds=file`、`kinds=skill` 及两者混排。

    技能候选与 agent 侧同源（同一会话工作区、同一份扫描逻辑），但走无副作用
    扫描 + 独立缓存，不会覆盖 agent 运行期的 `skill_registry` 单例状态。
    """
    requested = {part.strip().lower() for part in kinds.split(",") if part.strip()}
    root = resolve_workspace(session_id)
    payload: dict[str, Any] = {
        "workspace": str(root) if root else None,
        "items": [],
        "truncated": False,
    }
    if root is None:
        return payload

    needle = (q or "").strip().lower()
    items: list[dict[str, Any]] = []

    if "file" in requested:
        index = _get_index(root)
        matches: list[tuple[int, FileEntry]] = []
        for entry in index.entries:
            score = _score(entry, needle)
            if score is not None:
                matches.append((score, entry))
        matches.sort(key=lambda item: _sort_key(item[1], item[0]))
        items.extend(_serialize(entry) for _, entry in matches[:limit])
        payload["truncated"] = index.truncated

    if "skill" in requested:
        skill_matches: list[tuple[int, SkillEntry]] = []
        for entry in _get_skills(root):
            score = _score_skill(entry, needle)
            if score is not None:
                skill_matches.append((score, entry))
        skill_matches.sort(key=lambda item: _skill_sort_key(item[1], item[0]))
        items.extend(
            _serialize_skill(entry) for _, entry in skill_matches[:SKILL_LIMIT]
        )

    payload["items"] = items
    return payload


@router.get("/skill-names")
def list_skill_names(session_id: str | None = Query(None)):
    """返回当前会话工作区可见的**全部**技能名（供气泡渲染层使用）。

    气泡渲染需要判断正文里的 `/xxx` 到底是不是真技能——`见 /docs 目录` 的 `/docs`
    不该被标成技能胶囊。候选接口按 `SKILL_LIMIT` 截断（只保证"弹层前 N 条"），不能当
    全集用；本端点复用同一份无副作用扫描 + TTL 缓存，只回名称，开销可忽略。
    """
    root = resolve_workspace(session_id)
    if root is None:
        return {"workspace": None, "names": []}
    return {
        "workspace": str(root),
        "names": sorted(entry.name for entry in _get_skills(root)),
    }
