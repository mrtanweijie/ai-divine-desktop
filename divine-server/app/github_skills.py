from __future__ import annotations

import asyncio
import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .skills import (
    SkillMigrationError,
    _split_frontmatter,
    skill_registry,
    skills_target_dir,
)

ARCHIVE_LIMIT = 20 * 1024 * 1024
SKILL_SIZE_LIMIT = 10 * 1024 * 1024
MAX_PREVIEW_CHARS = 6000
MAX_FILES_IN_PREVIEW = 80


def parse_repo_url(raw: str) -> dict[str, str] | None:
    text = (raw or "").strip()
    if not text:
        return None
    text = re.sub(r"\.git\s*$", "", text).rstrip("/")
    pattern = (
        r"(?:(?:https?://(?:www\.)?(?P<host>[^/\s?#]+)/)"
        r"|(?:git@(?P<git_host>[^:\s]+):))?"
        r"(?P<owner>[^/\s?#]+)/(?P<repo>[^/\s?#]+)"
    )
    match = re.search(pattern, text)
    if not match:
        return None
    owner = match.group("owner").strip()
    repo = match.group("repo").strip()
    host = (
        match.group("host") or match.group("git_host") or "github.com"
    ).lower()
    host = re.sub(r"^www\.", "", host)
    if host not in {"github.com", "gitee.com"}:
        return None
    ref = None
    tail = text[match.end() :]
    tree = re.match(r"/(?:tree|blob)/(.+?)(?:/|$)", tail)
    if tree:
        ref = tree.group(1).strip("/")
    else:
        tag = re.match(r"/releases/tag/(.+?)(?:/|$)", tail)
        if tag:
            ref = tag.group(1).strip("/")
    if not owner or not repo:
        return None
    return {
        "host": host,
        "owner": owner,
        "repo": repo,
        "ref": ref or "",
    }


async def _default_branch(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    host: str = "github.com",
) -> str:
    try:
        if host == "gitee.com":
            url = f"https://gitee.com/api/v5/repos/{owner}/{repo}"
        else:
            url = f"https://api.github.com/repos/{owner}/{repo}"
        response = await client.get(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ai-divine",
            },
        )
        if response.status_code == 200:
            branch = response.json().get("default_branch")
            if branch:
                return str(branch)
    except (httpx.HTTPError, ValueError):
        pass
    return "main"


async def _download_archive(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    ref: str = "",
    host: str = "github.com",
) -> bytes:
    if host == "gitee.com":
        repo_url = f"https://gitee.com/{owner}/{repo}"
        return await asyncio.to_thread(_clone_repo_archive, repo_url, ref)

    async def stream_bytes(
        url: str, headers: dict[str, str] | None = None
    ) -> bytes | None:
        try:
            async with client.stream(
                "GET", url, headers=headers, follow_redirects=True
            ) as response:
                if response.status_code != 200:
                    return None
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > ARCHIVE_LIMIT:
                        raise SkillMigrationError(
                            "仓库压缩包超过 20MB"
                        )
                    chunks.append(chunk)
                if not chunks:
                    return None
                return b"".join(chunks)
        except SkillMigrationError:
            raise
        except httpx.HTTPError:
            return None

    branch = ref or await _default_branch(client, owner, repo, host)
    refs: list[str] = []
    if ref:
        refs.append(ref)
        if not ref.startswith("refs/"):
            refs.append(f"refs/heads/{ref}")
            if ref.lower().startswith("v") or not re.fullmatch(
                r"[0-9a-f]{7,40}", ref
            ):
                refs.append(f"refs/tags/{ref}")
    else:
        refs = [branch, f"refs/heads/{branch}", "main", "master"]

    for candidate in dict.fromkeys(refs):
        url = (
            "https://codeload.github.com/"
            f"{owner}/{repo}/tar.gz/{quote(candidate)}"
        )
        content = await stream_bytes(url)
        if content is not None:
            return content

    fallback_ref = quote(ref or "HEAD")
    fallback_url = (
        f"https://api.github.com/repos/{owner}/{repo}/tarball/"
        f"{fallback_ref}"
    )
    content = await stream_bytes(fallback_url)
    if content is None:
        content = await stream_bytes(
            fallback_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ai-divine",
            },
        )
    if content is not None:
        return content
    raise SkillMigrationError(
        "拉取 GitHub 仓库失败，请检查地址、分支或网络连接"
    )


def _dir_to_tar_gz(root: Path, prefix: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in sorted(root.rglob("*")):
            rel_path = path.relative_to(root)
            if ".git" in rel_path.parts:
                continue
            rel = rel_path.as_posix()
            arcname = f"{prefix}/{rel}"
            if path.is_symlink():
                info = tarfile.TarInfo(arcname)
                info.type = tarfile.SYMTYPE
                info.linkname = os.readlink(path)
                archive.addfile(info)
            elif path.is_file():
                info = tarfile.TarInfo(arcname)
                info.size = path.stat().st_size
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
    return buffer.getvalue()


def _clone_repo_archive(repo_url: str, ref: str) -> bytes:
    temp_root = Path(tempfile.mkdtemp(prefix="divine-skill-"))
    target = temp_root / "repo"
    try:
        shallow_ok = False
        command = ["git", "clone", "--depth", "1"]
        if ref:
            command.extend(["--branch", ref])
        command.extend([repo_url, str(target)])
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            raise SkillMigrationError("克隆仓库超时") from exc
        shallow_ok = result.returncode == 0
        if not shallow_ok:
            fallback = ["git", "clone", repo_url, str(target)]
            try:
                result = subprocess.run(
                    fallback,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
            except subprocess.TimeoutExpired as exc:
                raise SkillMigrationError("克隆仓库超时") from exc
        if result.returncode == 0 and ref and not shallow_ok:
            checkout = subprocess.run(
                ["git", "-C", str(target), "checkout", ref],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if checkout.returncode != 0:
                raise SkillMigrationError(
                    f"克隆仓库失败，无法切换到 {ref}: {checkout.stderr.strip()}"
                )
        if result.returncode != 0 or not target.is_dir():
            detail = (result.stderr or "").strip() or "未知错误"
            raise SkillMigrationError(f"克隆仓库失败: {detail[:300]}")
        name = repo_url.rstrip("/").split("/")[-1] or "repo"
        prefix = re.sub(r"[^\w.-]+", "-", f"{name}-{ref or 'default'}")
        return _dir_to_tar_gz(target, prefix)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def _root_prefix(paths: list[str]) -> str:
    top_level: set[str] = set()
    for path in paths:
        if "/" in path:
            top_level.add(path.split("/", 1)[0])
    if len(top_level) != 1:
        return ""
    prefix = next(iter(top_level)) + "/"
    if all(path.startswith(prefix) for path in paths):
        return prefix
    return ""


def _safe_relative(path: str) -> Path | None:
    parts = [part for part in path.replace("\\", "/").split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    rel = Path(*parts)
    if rel.is_absolute():
        return None
    return rel


def _member_text(tf: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    try:
        handle = tf.extractfile(member)
        if handle is None:
            return ""
        raw = handle.read()
    except (OSError, tarfile.TarError):
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _inspect_archive(content: bytes, owner: str, repo: str) -> dict[str, Any]:
    try:
        archive = tarfile.open(fileobj=io.BytesIO(content), mode="r:gz")
    except tarfile.TarError as exc:
        raise SkillMigrationError(f"GitHub 压缩包解析失败: {exc}") from exc

    with archive as tf:
        members = [member for member in tf.getmembers() if member.isfile()]
        prefix = _root_prefix([member.name for member in members])
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for member in members:
            raw_rel = member.name[len(prefix) :] if prefix else member.name
            rel = _safe_relative(raw_rel)
            if rel is None:
                continue
            parts = rel.parts
            if len(parts) == 1 and parts[0] == "SKILL.md":
                skill_path = ""
                fallback_name = repo
            elif (
                len(parts) >= 3
                and parts[0] == "skills"
                and parts[-1] == "SKILL.md"
            ):
                skill_path = "/".join(parts[:-1])
                fallback_name = parts[-2] if len(parts) >= 3 else repo
            elif (
                len(parts) >= 4
                and parts[0] == ".claude"
                and parts[1] == "skills"
                and parts[-1] == "SKILL.md"
            ):
                skill_path = "/".join(parts[:-1])
                fallback_name = parts[-2] if len(parts) >= 4 else repo
            else:
                continue
            if skill_path in seen:
                continue
            seen.add(skill_path)

            text = _member_text(tf, member)
            frontmatter, body = _split_frontmatter(text)
            name = str(frontmatter.get("name") or fallback_name).strip()
            description = str(
                frontmatter.get("description") or ""
            ).strip()[:200]
            files: list[str] = []
            total_size = 0
            base = prefix + (skill_path + "/" if skill_path else "")
            for candidate_member in members:
                if not candidate_member.name.startswith(base):
                    continue
                file_rel = _safe_relative(
                    candidate_member.name[len(base) :]
                )
                if file_rel is None:
                    continue
                files.append(str(file_rel))
                total_size += candidate_member.size
                if len(files) >= MAX_FILES_IN_PREVIEW:
                    break
            requirements = ""
            requirements_path = prefix + (
                f"{skill_path}/requirements.txt" if skill_path else "requirements.txt"
            )
            requirements_member = next(
                (
                    item
                    for item in members
                    if item.name == requirements_path
                ),
                None,
            )
            if requirements_member is not None:
                requirements = _member_text(tf, requirements_member)[:2000]
            candidates.append(
                {
                    "name": name or fallback_name,
                    "skill_path": skill_path,
                    "description": description,
                    "preview": (body.strip() or text.strip())[
                        :MAX_PREVIEW_CHARS
                    ],
                    "files": files,
                    "requirements": requirements,
                    "size": total_size,
                }
            )

    if not candidates:
        raise SkillMigrationError("仓库中没有找到 SKILL.md")
    return {
        "repo": f"{owner}/{repo}",
        "skills": candidates,
    }


async def preview_skill_repo(
    repo_url: str, ref: str | None = None
) -> dict[str, Any]:
    parsed = parse_repo_url(repo_url)
    if parsed is None:
        raise SkillMigrationError("无法识别的 GitHub 仓库地址")
    timeout = httpx.Timeout(30.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        content = await _download_archive(
            client,
            parsed["owner"],
            parsed["repo"],
            ref or parsed["ref"] or "",
            parsed["host"],
        )
    return _inspect_archive(
        content, parsed["owner"], parsed["repo"]
    )


def _extract_skill_files(
    archive_path: Path | None,
    archive_bytes: bytes,
    prefix: str,
    skill_path: str,
    destination: Path,
) -> list[str]:
    if archive_path is not None:
        handle: Any = tarfile.open(archive_path, mode="r:gz")
    else:
        handle = tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz")
    copied: list[str] = []
    total_size = 0
    with handle as tf:
        members = [member for member in tf.getmembers() if member.isfile()]
        base = prefix + (skill_path + "/" if skill_path else "")
        for member in members:
            if not member.name.startswith(base):
                continue
            if member.issym() or member.islnk():
                continue
            file_rel = _safe_relative(member.name[len(base) :])
            if file_rel is None:
                continue
            total_size += member.size
            if total_size > SKILL_SIZE_LIMIT:
                raise SkillMigrationError("技能文件超过 10MB，已停止安装")
            target = destination / file_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                source = tf.extractfile(member)
                if source is None:
                    continue
                with target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                copied.append(str(file_rel))
            except (OSError, tarfile.TarError) as exc:
                raise SkillMigrationError(
                    f"技能文件写入失败: {file_rel}: {exc}"
                ) from exc
    return copied


async def install_skill_repo(
    repo_url: str,
    project_root: Path,
    skill_path: str | None = None,
    ref: str | None = None,
    target: str = "project",
) -> dict[str, Any]:
    parsed = parse_repo_url(repo_url)
    if parsed is None:
        raise SkillMigrationError("无法识别的 GitHub 仓库地址")
    timeout = httpx.Timeout(30.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        content = await _download_archive(
            client,
            parsed["owner"],
            parsed["repo"],
            ref or parsed["ref"] or "",
            parsed["host"],
        )
    info = _inspect_archive(content, parsed["owner"], parsed["repo"])
    skills = info["skills"]
    selected = None
    if len(skills) == 1 and not skill_path:
        selected = skills[0]
    else:
        wanted = (skill_path or "").strip()
        for candidate in skills:
            if candidate["skill_path"] == wanted:
                selected = candidate
                break
        if selected is None and wanted:
            for candidate in skills:
                if candidate["name"] == wanted:
                    selected = candidate
                    break
    if selected is None:
        names = ", ".join(str(item["skill_path"]) for item in skills)
        raise SkillMigrationError(
            "仓库包含多个技能，请传入 skill_path 选择："
            + names
        )

    target_dir = skills_target_dir(project_root, target)
    destination = target_dir / str(selected["name"])
    if destination.exists():
        raise SkillMigrationError(
            f"技能 {selected['name']} 已存在，跳过安装"
        )
    target_dir.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)

    prefix = ""
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tf:
            paths = [
                member.name
                for member in tf.getmembers()
                if member.isfile()
            ]
        prefix = _root_prefix(paths)
        copied = _extract_skill_files(
            None,
            content,
            prefix,
            str(selected["skill_path"]),
            destination,
        )
    except tarfile.TarError as exc:
        raise SkillMigrationError(
            f"GitHub 压缩包解析失败: {exc}"
        ) from exc

    skill_registry.refresh(project_root)
    return {
        "ok": True,
        "name": str(selected["name"]),
        "repo": str(info["repo"]),
        "skill_path": str(selected["skill_path"]),
        "target": target,
        "target_path": str(destination),
        "files": copied,
    }
