import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.gitignore import is_ignored, load_gitignore_rules  # noqa: E402


def run_tool(workspace: Path, params: dict) -> dict:
    """Glob workspace files by pattern and return the tool result dict.

    Callable both from the CLI entrypoint and in-process (adapters run this
    directly inside ``asyncio.to_thread``).
    """
    pattern = str(params.get("pattern") or "").strip()
    raw_path = str(params.get("path") or "").strip()

    if not pattern:
        return {"success": False, "message": "pattern 不能为空"}

    base = workspace
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        base = candidate.resolve()
        try:
            base.relative_to(workspace)
        except ValueError:
            return {"success": False, "message": f"搜索路径越界: {base}"}
    if not base.is_dir():
        return {"success": False, "message": f"搜索目录不存在: {base}"}

    matchers, matcher_dirs = load_gitignore_rules(workspace, base)

    files = []
    truncated = False
    max_results = 500
    # rglob 支持 **/ 递归通配；结果按修改时间新→旧排序，方便定位最近改动。
    matches = [
        p
        for p in base.rglob(pattern)
        if p.is_file()
        and not any(part.startswith(".") for part in p.relative_to(base).parts)
    ]
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for path in matches:
        rel_parts = path.relative_to(base).parts
        # 目录型 gitignore 规则（如 "tests/"）需要逐级检查祖先目录。
        ignored = False
        for depth in range(1, len(rel_parts) + 1):
            if is_ignored(
                matchers,
                matcher_dirs,
                base,
                "/".join(rel_parts[:depth]),
                depth < len(rel_parts),
            ):
                ignored = True
                break
        if ignored:
            continue
        rel = path.relative_to(workspace).as_posix()
        files.append(
            {
                "path": rel,
                "name": path.name,
                "size": path.stat().st_size,
            }
        )
        if len(files) >= max_results:
            truncated = True
            break

    message = f"找到 {len(files)} 个文件"
    if truncated:
        message += f"（已截断，仅保留最近修改的 {max_results} 个）"
    return {
        "success": True,
        "message": message,
        "content": json.dumps(files, ensure_ascii=False),
        "truncated": truncated,
        "data": {"pattern": pattern, "count": len(files)},
    }


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    print(json.dumps(run_tool(workspace, params), ensure_ascii=False))


if __name__ == "__main__":
    main()
