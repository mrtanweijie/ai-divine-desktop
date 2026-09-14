"""工作区引用候选端点（A1）测试。

覆盖：目录扫描过滤、模糊匹配排序、空查询默认序、路径越界防护、路由挂载。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import workspace_files


def _make_tree(root: Path) -> None:
    (root / "src" / "components").mkdir(parents=True)
    (root / "src" / "index.tsx").write_text("export {}\n", encoding="utf-8")
    (root / "src" / "components" / "Button.tsx").write_text("x\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "react.js").write_text("x\n", encoding="utf-8")
    (root / "build").mkdir()
    (root / "build" / "out.js").write_text("x\n", encoding="utf-8")
    (root / ".hidden").write_text("x\n", encoding="utf-8")
    (root / "debug.log").write_text("x\n", encoding="utf-8")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    (root / ".gitignore").write_text("build/\n*.log\n", encoding="utf-8")


def _paths(payload: dict) -> list[str]:
    return [item["path"] for item in payload["items"]]


def test_mentions_filters_and_matches(monkeypatch, tmp_path):
    _make_tree(tmp_path)
    monkeypatch.setattr(workspace_files, "workspace_dir", lambda: tmp_path)
    workspace_files._index_cache.clear()

    payload = workspace_files.list_mentions(
        q="index", session_id=None, kinds="file", limit=20
    )

    assert payload["workspace"] == str(tmp_path.resolve())
    assert _paths(payload)[0] == "src/index.tsx"
    # 隐藏项 / 依赖目录 / gitignore 命中项都不应出现
    assert not any("node_modules" in path for path in _paths(payload))
    assert "build/out.js" not in _paths(payload)
    assert "debug.log" not in _paths(payload)


def test_mentions_empty_query_prefers_shallow(monkeypatch, tmp_path):
    _make_tree(tmp_path)
    monkeypatch.setattr(workspace_files, "workspace_dir", lambda: tmp_path)
    workspace_files._index_cache.clear()

    payload = workspace_files.list_mentions(
        q=None, session_id=None, kinds="file", limit=20
    )

    paths = _paths(payload)
    assert "build/out.js" not in paths
    assert "debug.log" not in paths
    # 根目录的 src 目录浅层优先于深层文件
    assert paths[0] == "src"
    assert "src/components/Button.tsx" in paths


def test_mentions_subsequence_fallback(monkeypatch, tmp_path):
    _make_tree(tmp_path)
    monkeypatch.setattr(workspace_files, "workspace_dir", lambda: tmp_path)
    workspace_files._index_cache.clear()

    payload = workspace_files.list_mentions(
        q="srcbut", session_id=None, kinds="file", limit=20
    )
    # 子序列 src + but 命中 src/components/Button.tsx
    assert "src/components/Button.tsx" in _paths(payload)


def test_mentions_missing_workspace_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_files, "workspace_dir", lambda: tmp_path / "nope")
    workspace_files._index_cache.clear()

    payload = workspace_files.list_mentions(
        q="a", session_id=None, kinds="file", limit=20
    )

    assert payload == {"workspace": None, "items": [], "truncated": False}


def test_ensure_within_blocks_escape(tmp_path):
    _make_tree(tmp_path)
    root = tmp_path.resolve()

    assert workspace_files.ensure_within(root, "src/index.tsx") is not None
    assert workspace_files.ensure_within(root, "../outside.txt") is None
    assert workspace_files.ensure_within(root, "") is None


def test_router_exposes_mentions_endpoint(monkeypatch, tmp_path):
    _make_tree(tmp_path)
    monkeypatch.setattr(workspace_files, "workspace_dir", lambda: tmp_path)
    workspace_files._index_cache.clear()

    app = FastAPI()
    app.include_router(workspace_files.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/workspace/mentions", params={"q": "index"})
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["path"] == "src/index.tsx"
    assert data["items"][0]["kind"] == "file"
