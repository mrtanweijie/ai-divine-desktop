"""chat.py 的 `@` 引用上下文构建（A2/A3）测试。

覆盖：元数据段渲染、失效/越界引用剔除、旧格式兼容、技能引用跳过、
请求模型对 mentions 的解析。
"""

from __future__ import annotations

from pathlib import Path

from app.api import chat
from app.schemas import MentionRef, StreamChatRequest


def _tree(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "index.tsx").write_text("export {}\n", encoding="utf-8")


def test_build_mention_context_injects_metadata(tmp_path):
    _tree(tmp_path)
    root = tmp_path.resolve()

    block, paths = chat._build_mention_context(
        [MentionRef(type="file", path="src/index.tsx")], root
    )

    assert "src/index.tsx" in block
    assert "read_file" in block
    assert str(root / "src" / "index.tsx") in paths


def test_build_mention_context_drops_invalid_refs(tmp_path):
    _tree(tmp_path)
    root = tmp_path.resolve()

    block, paths = chat._build_mention_context(
        [
            {"type": "file", "path": "missing.md"},
            {"type": "file", "path": "../../etc/passwd"},
        ],
        root,
    )

    assert block == ""
    assert paths == []


def test_build_mention_context_dedupes_and_marks_dir(tmp_path):
    _tree(tmp_path)
    root = tmp_path.resolve()

    block, paths = chat._build_mention_context(
        ["src", {"type": "file", "path": "src"}], root
    )

    assert block.count("- src/（目录）") == 1
    assert len(paths) == 1


def test_build_mention_context_accepts_legacy_strings(tmp_path):
    _tree(tmp_path)
    root = tmp_path.resolve()

    block, paths = chat._build_mention_context(["src/index.tsx"], root)

    assert "src/index.tsx" in block
    assert len(paths) == 1


def test_build_mention_context_skips_skill_mentions(tmp_path):
    _tree(tmp_path)

    block, paths = chat._build_mention_context(
        [{"type": "skill", "name": "demo-skill"}], tmp_path.resolve()
    )

    assert block == ""
    assert paths == []


def test_build_mention_context_without_workspace():
    block, paths = chat._build_mention_context(["src/index.tsx"], None)

    assert block == ""
    assert paths == []


def test_stream_chat_request_parses_mentions():
    request = StreamChatRequest(
        question="hi",
        mentions=["a.txt", {"type": "skill", "name": "demo"}],
    )

    assert [item.type for item in request.mentions] == ["file", "skill"]
    assert request.mentions[0].path == "a.txt"
    assert request.mentions[1].name == "demo"


def test_stream_chat_request_mentions_default_empty():
    assert StreamChatRequest(question="hi").mentions == []
