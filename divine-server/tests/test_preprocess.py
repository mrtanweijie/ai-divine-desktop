"""本地预整理（输入侧预处理）测试。

覆盖 docs/preprocess-feature-design.md 的触发规则与降级策略：
指针跳过 / 显式触发 / 自动触发 / 代码与表格跳过 / 多轮退化 / 模型不可用降级，
以及 organize() 的输出三关校验。
"""

from __future__ import annotations

from pathlib import Path


def _init(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    workspace_dir = tmp_path / "workspace"
    db_path = tmp_path / "preprocess.db"
    monkeypatch.setenv("DIVINE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(workspace_dir))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from app import db

    db.init_db()
    return Path(workspace_dir)


class FakeManager:
    """假的本地模型管理器：记录调用，按预设结果返回。"""

    def __init__(
        self,
        result: str = "[本地整理版]\n### 主题\n- 要点",
        ready: bool = True,
    ) -> None:
        self.result = result
        self.ready = ready
        self.calls: list[str] = []

    def is_ready(self) -> bool:
        return self.ready

    def organize(self, text: str, timeout: float = 30.0) -> str | None:
        self.calls.append(text)
        return self.result


def _patch_manager(monkeypatch, manager: FakeManager) -> None:
    monkeypatch.setattr(
        "app.agent.local_llm.get_manager", lambda: manager
    )


def _maybe_preprocess(text, session_id="s1", workspace=None):
    from app.agent.preprocess import maybe_preprocess

    return maybe_preprocess(text, session_id, workspace)


# ---------------------------------------------------------------------------
# 指针（链接 / 本地路径）跳过
# ---------------------------------------------------------------------------

def test_pointer_only_url_skips(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    text = "帮我整理这个链接 https://example.com/a"
    final, attachment, organized = _maybe_preprocess(
        text, workspace=tmp_path / "workspace"
    )
    assert final == text
    assert attachment is None
    assert organized is False
    assert manager.calls == []


def test_pointer_only_path_skips(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    text = "/Users/tan/Desktop/report.pdf"
    final, attachment, organized = _maybe_preprocess(
        text, workspace=tmp_path / "workspace"
    )
    assert final == text
    assert organized is False
    assert manager.calls == []


# ---------------------------------------------------------------------------
# 显式触发
# ---------------------------------------------------------------------------

def test_explicit_trigger_organizes(tmp_path, monkeypatch):
    ws = _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    text = "帮我整理这段：今天开会讨论了三个议题，第一是预算，第二是排期。"
    final, attachment, organized = _maybe_preprocess(
        text, workspace=ws
    )
    assert organized is True
    assert attachment is not None
    assert attachment.exists()
    assert attachment.read_text(encoding="utf-8") == text
    # 核对提示前缀 + 整理版
    assert final.startswith("（用户原文已保存为工作区附件")
    assert "[本地整理版]" in final
    assert manager.calls == [text]


def test_daily_organize_not_triggered(tmp_path, monkeypatch):
    """'帮我整理房间的计划'——日常'整理'，无文本指代词，不触发。"""
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    text = "帮我整理房间的计划"
    final, _, organized = _maybe_preprocess(
        text, workspace=tmp_path / "workspace"
    )
    assert final == text
    assert organized is False
    assert manager.calls == []


def test_explicit_manager_not_ready_falls_back(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    manager = FakeManager(ready=False)
    _patch_manager(monkeypatch, manager)
    text = "帮我整理这段：今天开会讨论了三个议题。"
    final, attachment, organized = _maybe_preprocess(
        text, workspace=tmp_path / "workspace"
    )
    assert final == text
    assert attachment is None
    assert organized is False


# ---------------------------------------------------------------------------
# 自动触发
# ---------------------------------------------------------------------------

_LONG_CJK = "这是需要整理的测试文本。" * 120  # ~1440 字 ≈ 1440 token


def test_auto_trigger_on_long_text(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    final, attachment, organized = _maybe_preprocess(
        _LONG_CJK, workspace=tmp_path / "workspace"
    )
    assert organized is True
    assert attachment is not None
    assert manager.calls == [_LONG_CJK]


def test_auto_not_triggered_below_threshold(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    text = "短文本，不该自动整理。"
    final, _, organized = _maybe_preprocess(
        text, workspace=tmp_path / "workspace"
    )
    assert final == text
    assert organized is False
    assert manager.calls == []


def test_code_skipped_in_auto(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    code = "```python\n" + "def f(x):\n    return x + 1\n" * 200 + "```"
    final, _, organized = _maybe_preprocess(
        code, workspace=tmp_path / "workspace"
    )
    assert final == code
    assert organized is False
    assert manager.calls == []


def test_table_skipped_in_auto(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    csv = "name,age,city\n" + "alice,30,beijing\n" * 150
    final, _, organized = _maybe_preprocess(
        csv, workspace=tmp_path / "workspace"
    )
    assert final == csv
    assert organized is False
    assert manager.calls == []


def test_disabled_skips_even_long_text(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)

    # 用 monkeypatch 覆写 load()，避免依赖共享的 settings_store 单例路径
    # （该单例的 path 在首次 import 时钉死，save() 会跨测试污染）
    from app.config import settings_store

    real_load = settings_store.load
    monkeypatch.setattr(
        settings_store,
        "load",
        lambda: {**real_load(), "local_llm_preprocess_enabled": False},
    )

    final, _, organized = _maybe_preprocess(
        _LONG_CJK, workspace=tmp_path / "workspace"
    )
    assert final == _LONG_CJK
    assert organized is False
    assert manager.calls == []


def test_multi_turn_regression_skips(tmp_path, monkeypatch):
    """第二轮发相同原文 → 与最近附件相似，不重复整理。"""
    ws = _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    text = "帮我整理这段：" + _LONG_CJK[:300]
    att_dir = ws / "sessions" / "s1" / "attachments"
    att_dir.mkdir(parents=True, exist_ok=True)
    (att_dir / "original-1.md").write_text(text, encoding="utf-8")

    final, attachment, organized = _maybe_preprocess(text, workspace=ws)
    assert final == text
    assert attachment is None
    assert organized is False
    assert manager.calls == []


def test_chunked_relabel_keeps_heading(tmp_path, monkeypatch):
    """分块整理：### 开头（无前缀标记）时前置分块标注，不吞掉原标题。"""
    _init(tmp_path, monkeypatch)
    manager = FakeManager(result="### 议题\n- 要点")
    _patch_manager(monkeypatch, manager)
    text = "这是需要整理的测试段落内容。" * 200  # 2800 字符 → 2 块
    final, _, organized = _maybe_preprocess(
        text, workspace=tmp_path / "workspace"
    )
    assert organized is True
    assert "[本地整理版（第 1/" in final
    assert "### 议题" in final
    assert "第 2/" in final


# ---------------------------------------------------------------------------
# 附件通道：大段粘贴文本（paste-*.txt）先本地整理再上云
# ---------------------------------------------------------------------------

def _maybe_preprocess_attachment(question, content, workspace, orig=None):
    from app.agent.preprocess import maybe_preprocess_attachment

    return maybe_preprocess_attachment(
        question, content, "s1", workspace, orig
    )


def test_attachment_explicit_organizes(tmp_path, monkeypatch):
    """"帮我整理" + 附件 → 附件即指代对象，显式触发。"""
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    content = "这是附件里的长文本内容。" * 60
    new_content, orig, organized = _maybe_preprocess_attachment(
        "帮我整理", content, tmp_path / "workspace", "/tmp/paste-x.txt"
    )
    assert organized is True
    assert new_content.startswith("（用户原文已保存为附件")
    assert "[本地整理版]" in new_content
    assert orig == "/tmp/paste-x.txt"  # 复用附件自身路径，不写新文件


def test_attachment_auto_organizes(tmp_path, monkeypatch):
    """无整理指令的大文本附件 → 自动触发。"""
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    content = "这是附件里的长文本内容。" * 120  # > 800 token
    new_content, orig, organized = _maybe_preprocess_attachment(
        "看看这个文件", content, tmp_path / "workspace"
    )
    assert organized is True
    assert orig is not None  # 无 file_path → 新写 original-*.md


def test_attachment_short_not_organized(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    content = "短内容。"
    new_content, orig, organized = _maybe_preprocess_attachment(
        "看看这个文件", content, tmp_path / "workspace"
    )
    assert organized is False
    assert new_content == content
    assert manager.calls == []


def test_attachment_code_skipped(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    content = "```python\n" + "def f(x):\n    return x + 1\n" * 200 + "```"
    new_content, _, organized = _maybe_preprocess_attachment(
        "看看这个文件", content, tmp_path / "workspace"
    )
    assert organized is False
    assert new_content == content


def test_attachment_empty_skipped(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)
    new_content, _, organized = _maybe_preprocess_attachment(
        "帮我整理", "   ", tmp_path / "workspace"
    )
    assert organized is False


def test_chat_attachment_parts_and_history(tmp_path, monkeypatch):
    """模拟 chat.py 附件循环：整理版替换附件内容，preprocess 部件落库，
    模型上下文拿到整理版 + 路径引用（不含原文全文），前端部件可读。"""
    ws = _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)

    from app import db
    from app.agent.preprocess import maybe_preprocess_attachment

    session = db.create_session(title="t")["id"]
    original = "1. 需求评审：讨论第一项。\n2. 技术选型：讨论第二项。\n" * 60
    new_content, att_orig, organized = maybe_preprocess_attachment(
        "帮我整理",
        original,
        session,
        ws,
        "/tmp/paste-xxx.txt",  # 附件自身路径
    )
    assert organized is True
    assert att_orig == "/tmp/paste-xxx.txt"

    message = db.add_message(session, "user", "帮我整理")
    db.add_message_part(
        message["id"],
        "file",
        __import__("json").dumps(
            {
                "name": "paste-xxx.txt",
                "path": att_orig,
                "content": new_content,  # 整理版替换原文进上下文
            },
            ensure_ascii=False,
        ),
        order=0,
    )
    db.add_message_part(
        message["id"],
        "preprocess",
        __import__("json").dumps(
            {
                "organized": True,
                "original_path": att_orig,
                "original": original,
            },
            ensure_ascii=False,
        ),
        order=1,
    )

    history = db.history_for_model(session)
    user_turn = next(m for m in history if m["role"] == "user")
    assert "[本地整理版]" in user_turn["content"]
    assert "用户原文已保存为附件" in user_turn["content"]
    assert "文件本地路径：/tmp/paste-xxx.txt" in user_turn["content"]
    assert original not in user_turn["content"]  # 原文不进上下文

    page = db.load_session_page(session)
    msg = page["messages"][-1]
    types = {part["type"] for part in msg["parts"]}
    assert "preprocess" in types and "file" in types
    import json as _json

    meta = _json.loads(
        next(p for p in msg["parts"] if p["type"] == "preprocess")["content"]
    )
    assert meta["organized"] is True
    assert meta["original"] == original
    assert meta["original_path"] == "/tmp/paste-xxx.txt"


# ---------------------------------------------------------------------------
# organize() 输出三关校验（local_llm.LocalLLMManager.organize）
# ---------------------------------------------------------------------------

class AutoStartManager(FakeManager):
    """模拟模型不在 → start() 后就绪（验证自动拉起）。"""

    def __init__(self, result: str = "[本地整理版]\n### 主题\n- 要点") -> None:
        super().__init__(result=result, ready=False)
        self.started: list[tuple[str, str]] = []

    def get_status(self) -> dict:
        return {
            "installed_models": [
                {
                    "id": "qwen2.5-1.5b-instruct-q4km",
                    "registry_id": "qwen2.5-1.5b-instruct-q4km",
                    "path": "/fake/models/qwen2.5-1.5b.gguf",
                }
            ]
        }

    def start(self, model_id: str, model_path: str, wait_s: float = 3.0):
        self.started.append((model_id, model_path))
        self.ready = True
        return True, ""

    def is_ready(self) -> bool:
        return self.ready


def test_auto_start_when_model_down(tmp_path, monkeypatch):
    """模型没跑时预整理自动拉起（选择 1.5B），拉起后正常整理。"""
    _init(tmp_path, monkeypatch)
    manager = AutoStartManager()
    _patch_manager(monkeypatch, manager)
    text = "帮我整理这段：今天开会讨论了三个议题。第一是预算，第二是排期。" * 30
    final, attachment, organized = _maybe_preprocess(
        text, workspace=tmp_path / "workspace"
    )
    assert organized is True
    assert attachment is not None
    assert manager.started == [
        ("qwen2.5-1.5b-instruct-q4km", "/fake/models/qwen2.5-1.5b.gguf")
    ]


def test_auto_start_no_model_falls_back(tmp_path, monkeypatch):
    """没有已装模型时自动拉起失败 → 原样上云。"""
    _init(tmp_path, monkeypatch)
    manager = FakeManager(ready=False)
    manager.get_status = lambda: {"installed_models": []}  # type: ignore[method-assign]
    _patch_manager(monkeypatch, manager)
    text = "帮我整理这段：今天开会讨论了三个议题。" * 30
    final, _, organized = _maybe_preprocess(
        text, workspace=tmp_path / "workspace"
    )
    assert final == text
    assert organized is False


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _make_choice(content: str, finish_reason: str = "stop") -> dict:
    return {
        "choices": [
            {"finish_reason": finish_reason, "message": {"content": content}}
        ]
    }


def _manager_with_post(monkeypatch, tmp_path, payload):
    from app.agent.local_llm import LocalLLMManager

    manager = LocalLLMManager(str(tmp_path / "data"), port=8016)
    monkeypatch.setattr(manager, "is_ready", lambda: True)
    monkeypatch.setattr(
        "app.agent.local_llm.requests.post",
        lambda *a, **k: _FakeResponse(payload),
    )
    return manager


def test_organize_valid_output(tmp_path, monkeypatch):
    manager = _manager_with_post(
        monkeypatch,
        tmp_path,
        _make_choice("[本地整理版]\n### 主题\n- 要点"),
    )
    result = manager.organize("原文内容" * 50)
    assert result == "[本地整理版]\n### 主题\n- 要点"


def test_organize_rejects_wrong_prefix(tmp_path, monkeypatch):
    manager = _manager_with_post(
        monkeypatch, tmp_path, _make_choice("随便说说")
    )
    assert manager.organize("原文内容" * 50) is None


def test_organize_accepts_heading_without_marker(tmp_path, monkeypatch):
    """小模型常见表现：内容格式正确但漏掉 [本地整理版] 前缀（### 开头）→ 仍合格。"""
    manager = _manager_with_post(
        monkeypatch,
        tmp_path,
        _make_choice("### 会议议题\n- 预算问题"),
    )
    result = manager.organize("原文内容" * 50)
    assert result == "### 会议议题\n- 预算问题"


def test_organize_rejects_truncated(tmp_path, monkeypatch):
    manager = _manager_with_post(
        monkeypatch,
        tmp_path,
        _make_choice("[本地整理版]\n### 主题\n- 要点", finish_reason="length"),
    )
    assert manager.organize("原文内容" * 50) is None


def test_organize_rejects_verbose_unstructured(tmp_path, monkeypatch):
    """输出显著长于原文（>1.5x+200）且无 ### 标题 → 视为废话整理，丢弃。"""
    manager = _manager_with_post(
        monkeypatch,
        tmp_path,
        _make_choice("[本地整理版]\n" + "废话" * 260),
    )
    # 原文 50*4=200 字，阈值 200*1.5+200=500；输出 529 字无标题 → 丢弃
    assert manager.organize("原文内容" * 50) is None


def test_organize_returns_none_when_not_ready(tmp_path, monkeypatch):
    from app.agent.local_llm import LocalLLMManager

    manager = LocalLLMManager(str(tmp_path / "data"), port=8016)
    monkeypatch.setattr(manager, "is_ready", lambda: False)
    assert manager.organize("原文内容" * 50) is None


# ---------------------------------------------------------------------------
# 聊天链路集成：预整理 → 消息部件落库 → 模型上下文 / 前端部件
# ---------------------------------------------------------------------------

def test_chat_message_parts_and_history(tmp_path, monkeypatch):
    """整理版进模型上下文（含路径引用、不含原文全文）；preprocess 部件供前端。"""
    ws = _init(tmp_path, monkeypatch)
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)

    from app import db
    from app.agent.preprocess import maybe_preprocess

    session = db.create_session(title="t")["id"]
    original = "今天开会讨论了三个议题。" * 120  # 超阈值，触发自动整理
    final_text, original_path, organized = maybe_preprocess(
        original, session, ws
    )
    assert organized is True
    assert original_path is not None

    message = db.add_message(session, "user", final_text)
    db.add_message_part(
        message["id"],
        "file",
        __import__("json").dumps(
            {
                "name": "原文附件",
                "path": str(original_path),
                "size": original_path.stat().st_size,
                "preprocess_original": True,
            },
            ensure_ascii=False,
        ),
        order=0,
    )
    db.add_message_part(
        message["id"],
        "preprocess",
        __import__("json").dumps(
            {
                "organized": True,
                "original_path": str(original_path),
                "original": original[:12000],
            },
            ensure_ascii=False,
        ),
        order=1,
    )

    # 模型上下文：user 消息 = 核对提示 + 整理版 + 原文路径引用；不含原文全文
    history = db.history_for_model(session)
    user_turn = next(m for m in history if m["role"] == "user")
    assert "[本地整理版]" in user_turn["content"]
    assert "用户原文已保存为工作区附件" in user_turn["content"]
    assert "文件本地路径：" in user_turn["content"]
    assert str(original_path) in user_turn["content"]
    assert original not in user_turn["content"]  # 决策 3：不注入原文全文

    # 前端数据：preprocess 部件 + file 部件都在
    page = db.load_session_page(session)
    msg = page["messages"][-1]
    types = {part["type"] for part in msg["parts"]}
    assert "preprocess" in types
    assert "file" in types
    preprocess_part = next(
        p for p in msg["parts"] if p["type"] == "preprocess"
    )
    import json as _json

    meta = _json.loads(preprocess_part["content"])
    assert meta["organized"] is True
    assert meta["original"] == original[:12000]
    assert meta["original_path"] == str(original_path)
