"""``render_ui`` / A2UI 校验器与版本边界的测试。

设计文档：``docs/design/028-a2ui-integration-20261009.md`` §4 / §5.1 / §9。

覆盖点与 044 §9.1 的三层防线对齐（这里只测 L2，L3 在前端）：

* 合法样例通过（含 §4.4 的 cost-panel 样例）；
* 未知组件 / 未知属性 / 引用缺失 / 成环 / 深度超限 / 组件数超限 /
  Table 行数超限 / 未登记动作 / 坏 catalogId / 缺 root —— 全部**被拒**，
  且报错文本可读、含合法枚举（模型据此自纠）；
* S5 富媒体（Chart / Graph / FileList）：Chart 顶层配色被剥而嵌套不动、
  Chart/Graph 单类各限 1、Graph 复用 render_graph 校验器、FileList 路径安全；
* 不可达组件只告警并从归一化结果里裁掉；
* v0.9.1 消息信封快照（防止有人手改协议层而不动测试）。
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from app.tools.ui.catalog import (
    A2UI_VERSION,
    CATALOG_ID,
    MAX_CHART_OPTION_CHARS,
    MAX_FILE_ITEMS,
    MAX_TABLE_ROWS,
    catalog_document,
)
from app.tools.ui.validator import validate_ui_surface
from app.tools.ui.versions.v0_9_1 import to_messages, to_sse_payload

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "tools" / "ui" / "divine_catalog.json"
)


def sample_surface() -> dict:
    """044 §4.4 的样例（Chart 属 S5，此处以 Steps 代位保持规模相近）。"""
    return {
        "surfaceId": "cost-panel",
        "title": "本月成本结构",
        "actions": ["recalc", "export_pdf"],
        "components": [
            {"id": "root", "component": "Column", "gap": "md",
             "children": ["hdr", "kpi", "tbl", "ops"]},
            {"id": "hdr", "component": "Text", "text": "本月成本结构", "variant": "h3"},
            {"id": "kpi", "component": "Row", "gap": "sm", "children": ["k1", "k2"]},
            {"id": "k1", "component": "Badge", "text": "总成本 ¥128.4 万", "tone": "default"},
            {"id": "k2", "component": "Badge", "text": "环比 -4.2%", "tone": "success"},
            {"id": "tbl", "component": "Table", "maxHeight": 320,
             "columns": [{"key": "name", "title": "科目"},
                         {"key": "amount", "title": "金额"}],
             "rows": {"path": "/rows"}},
            {"id": "ops", "component": "Row", "gap": "sm",
             "children": ["labor", "recalc", "export"]},
            {"id": "labor", "component": "NumberField", "label": "人力成本占比 (%)",
             "value": {"path": "/target/labor"}, "min": 0, "max": 100, "step": 1},
            {"id": "recalc", "component": "Button", "variant": "primary", "text": "重新测算",
             "action": {"name": "recalc",
                        "context": [{"key": "labor", "value": {"path": "/target/labor"}}]}},
            {"id": "export", "component": "Button", "variant": "ghost", "text": "导出 PDF",
             "action": {"name": "export_pdf"}},
        ],
        "data": {
            "rows": [
                {"name": "人力", "amount": "38.5 万"},
                {"name": "算力", "amount": "42.1 万"},
            ],
            "target": {"labor": 30},
        },
    }


def _root_only(children: list[str], **extra) -> dict:
    surface = {
        "surfaceId": "s1",
        "components": [{"id": "root", "component": "Column", "children": children}, *extra.pop("rest", [])],
        "data": extra.pop("data", {}),
    }
    surface.update(extra)
    return surface


# --------------------------------------------------------------------------
# 合法路径
# --------------------------------------------------------------------------


def test_sample_surface_passes() -> None:
    result = validate_ui_surface(sample_surface(), catalog_id=CATALOG_ID)
    assert result.ok, result.summary()
    assert not result.errors
    normalized = result.normalized or {}
    assert normalized["surfaceId"] == "cost-panel"
    # 归一化保留全部 10 个可达组件，且顺序与声明一致
    assert [c["id"] for c in normalized["components"]] == [
        "root", "hdr", "kpi", "k1", "k2", "tbl", "ops", "labor", "recalc", "export",
    ]
    # 未知键不被带入
    assert set(normalized) <= {"surfaceId", "title", "components", "data", "actions"}


def test_builtin_action_alone_is_enough() -> None:
    surface = _root_only(
        ["btn"],
        rest=[{"id": "btn", "component": "Button", "text": "提交",
               "action": {"name": "submit"}}],
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert result.ok, result.summary()


def test_binding_resolves_against_data() -> None:
    surface = _root_only(
        ["t"],
        rest=[{"id": "t", "component": "Text", "text": {"path": "/msg"}}],
        data={"msg": "hi"},
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert result.ok, result.summary()


# --------------------------------------------------------------------------
# 拒绝路径：必须硬报错，且报错可照抄自纠
# --------------------------------------------------------------------------


def test_unknown_component_rejected_with_legal_enum() -> None:
    surface = _root_only(["x"], rest=[{"id": "x", "component": "Textt", "text": "a"}])
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    summary = result.summary()
    assert "Textt" in summary
    assert "Column" in summary and "Button" in summary  # 合法枚举被回灌


def test_unknown_prop_rejected() -> None:
    surface = _root_only(
        ["x"], rest=[{"id": "x", "component": "Text", "text": "a", "color": "#fff"}]
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "color" in result.summary()
    assert "variant" in result.summary()  # 列出了 Text 允许的属性


def test_missing_reference_rejected() -> None:
    surface = _root_only(["nope"])
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "nope" in result.summary()


def test_missing_root_rejected() -> None:
    surface = {
        "surfaceId": "s1",
        "components": [{"id": "a", "component": "Text", "text": "x"}],
        "data": {},
    }
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "root" in result.summary()


def test_cycle_rejected() -> None:
    surface = {
        "surfaceId": "s1",
        "components": [
            {"id": "root", "component": "Column", "children": ["a"]},
            {"id": "a", "component": "Column", "children": ["root"]},
        ],
        "data": {},
    }
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "环" in result.summary()


def test_depth_exceeded_rejected() -> None:
    # root -> c1 -> ... -> c13：深度 14 > MAX_DEPTH(12)
    components = [{"id": "root", "component": "Column", "children": ["c1"]}]
    for i in range(1, 14):
        components.append(
            {"id": f"c{i}", "component": "Column", "children": [f"c{i + 1}"]}
        )
    components.append({"id": "c14", "component": "Text", "text": "deep"})
    result = validate_ui_surface(
        {"surfaceId": "s1", "components": components, "data": {}}, catalog_id=CATALOG_ID
    )
    assert not result.ok
    assert "深度" in result.summary()


def test_component_count_limit() -> None:
    children = [f"c{i}" for i in range(130)]
    components = [{"id": "root", "component": "Column", "children": children}]
    components += [{"id": cid, "component": "Text", "text": "x"} for cid in children]
    result = validate_ui_surface(
        {"surfaceId": "s1", "components": components, "data": {}}, catalog_id=CATALOG_ID
    )
    assert not result.ok
    assert "120" in result.summary()


def test_table_rows_limit_literal_and_binding() -> None:
    rows = [{"a": i} for i in range(MAX_TABLE_ROWS + 1)]
    lit = _root_only(
        ["t"],
        rest=[{"id": "t", "component": "Table",
               "columns": [{"key": "a", "title": "A"}], "rows": rows}],
    )
    assert not validate_ui_surface(lit, catalog_id=CATALOG_ID).ok

    bound = _root_only(
        ["t"],
        rest=[{"id": "t", "component": "Table",
               "columns": [{"key": "a", "title": "A"}], "rows": {"path": "/rows"}}],
        data={"rows": rows},
    )
    result = validate_ui_surface(bound, catalog_id=CATALOG_ID)
    assert not result.ok
    assert str(MAX_TABLE_ROWS) in result.summary()


def test_undeclared_domain_action_rejected() -> None:
    surface = _root_only(
        ["btn"], rest=[{"id": "btn", "component": "Button", "text": "算",
                        "action": {"name": "recalc"}}]
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "recalc" in result.summary()
    assert "surface.actions" in result.summary()


def test_bad_catalog_id_rejected() -> None:
    result = validate_ui_surface(sample_surface(), catalog_id="https://evil/x.json")
    assert not result.ok
    assert "不被支持" in result.summary()


def test_unknown_top_level_key_rejected() -> None:
    surface = sample_surface()
    surface["theme"] = {"primary": "#000"}
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "theme" in result.summary()  # 样式/主题注入必须被挡在门外（§9.4）


def test_binding_to_missing_path_rejected() -> None:
    surface = _root_only(
        ["t"], rest=[{"id": "t", "component": "Text", "text": {"path": "/nope"}}],
        data={"msg": "hi"},
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "/nope" in result.summary()
    assert "msg" in result.summary()  # 提示 data 现有顶层键


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "javascript:alert(1)", "/etc/passwd", "../../secret.png"]
)
def test_unsafe_image_url_rejected(url: str) -> None:
    surface = _root_only(
        ["img"], rest=[{"id": "img", "component": "Image", "url": url, "aspectRatio": 1.5}]
    )
    assert not validate_ui_surface(surface, catalog_id=CATALOG_ID).ok


def test_progress_out_of_range_rejected() -> None:
    surface = _root_only(["p"], rest=[{"id": "p", "component": "Progress", "value": 1.5}])
    assert not validate_ui_surface(surface, catalog_id=CATALOG_ID).ok


def test_enum_value_rejected() -> None:
    surface = _root_only(
        ["b"], rest=[{"id": "b", "component": "Badge", "text": "x", "tone": "mauve"}]
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "success" in result.summary()


def test_rich_media_limit() -> None:
    """重组件同屏总量上限（Chart/Graph 合计 ≤ 2，044 §4.3）。"""
    chart = {"id": "c", "component": "Chart", "option": {"series": []}}
    graph = {"id": "g", "component": "Graph", "ir": _valid_graph_ir()}
    ok = _root_only(["c", "g"], rest=[chart, graph])
    assert validate_ui_surface(ok, catalog_id=CATALOG_ID).ok  # 1+1 合规

    # 3 个重组件超总量上限
    over = _root_only(
        ["c", "c2", "g"],
        rest=[chart, {**chart, "id": "c2"}, graph],
    )
    result = validate_ui_surface(over, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "重组件" in result.summary()


# --------------------------------------------------------------------------
# S5 富媒体：Chart / Graph / FileList
# --------------------------------------------------------------------------


def _valid_graph_ir() -> dict:
    return {
        "kind": "flow",
        "meta": {"title": "t"},
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        "edges": [{"id": "e1", "source": "a", "target": "b"}],
    }


def test_chart_accepts_option_object() -> None:
    surface = _root_only(
        ["c"],
        rest=[
            {
                "id": "c",
                "component": "Chart",
                "option": {"xAxis": {"type": "category"}, "series": [{"type": "bar"}]},
                "height": 300,
            }
        ],
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert result.ok, result.summary()


def test_chart_strips_theme_keys_at_top_level() -> None:
    """配色/动画是"多此一举"而非"参数错误"：剥掉，不报错（044 §9.4）。"""
    surface = _root_only(
        ["c"],
        rest=[
            {
                "id": "c",
                "component": "Chart",
                "option": {
                    "color": ["#ff0000"],
                    "backgroundColor": "#000",
                    "textStyle": {"color": "#fff"},
                    "animation": False,
                    "xAxis": {"type": "category"},
                    "series": [{"type": "bar", "data": [1, 2]}],
                },
            }
        ],
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert result.ok, result.summary()
    chart = next(c for c in (result.normalized or {})["components"] if c["id"] == "c")
    # 顶层展示性键全部被剥掉
    for key in ("color", "backgroundColor", "textStyle", "animation"):
        assert key not in chart["option"]
    # 业务键原样保留
    assert chart["option"]["xAxis"] == {"type": "category"}
    assert chart["option"]["series"] == [{"type": "bar", "data": [1, 2]}]


def test_chart_does_not_strip_nested_series_style() -> None:
    """只剥顶层：深挖 series[].itemStyle 会把"props 转发"做成第二套主题引擎。"""
    surface = _root_only(
        ["c"],
        rest=[
            {
                "id": "c",
                "component": "Chart",
                "option": {"series": [{"type": "bar", "itemStyle": {"color": "#abc"}}]},
            }
        ],
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert result.ok, result.summary()
    chart = next(c for c in (result.normalized or {})["components"] if c["id"] == "c")
    assert chart["option"]["series"][0]["itemStyle"] == {"color": "#abc"}


def test_chart_option_must_be_object() -> None:
    surface = _root_only(
        ["c"], rest=[{"id": "c", "component": "Chart", "option": "graph TD; A-->B"}]
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "ECharts option" in result.summary()


def test_chart_option_size_limit() -> None:
    huge = {"series": [{"data": ["x" * 200] * (MAX_CHART_OPTION_CHARS // 200 + 50)}]}
    surface = _root_only(["c"], rest=[{"id": "c", "component": "Chart", "option": huge}])
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert str(MAX_CHART_OPTION_CHARS) in result.summary()


def test_two_charts_rejected_by_per_kind_limit() -> None:
    chart = {"id": "c", "component": "Chart", "option": {"series": []}}
    surface = _root_only(["c", "c2"], rest=[chart, {**chart, "id": "c2"}])
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "Chart" in result.summary()


def test_graph_accepts_valid_ir() -> None:
    surface = _root_only(
        ["g"], rest=[{"id": "g", "component": "Graph", "ir": _valid_graph_ir()}]
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert result.ok, result.summary()


def test_graph_reuses_render_graph_validator() -> None:
    """面板里的图与独立 render_graph 必须同一结论（不写第二份规则）。"""
    surface = _root_only(["g"], rest=[{"id": "g", "component": "Graph", "ir": {}}])
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "GraphIR" in result.summary()


def test_graph_non_object_rejected() -> None:
    surface = _root_only(["g"], rest=[{"id": "g", "component": "Graph", "ir": "a->b"}])
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "GraphIR" in result.summary()


def test_file_list_accepts_items() -> None:
    surface = _root_only(
        ["f"],
        rest=[
            {
                "id": "f",
                "component": "FileList",
                "files": [
                    {"name": "report.pdf", "path": "output/report.pdf", "size": 10240},
                    {"name": "chart.png"},
                ],
            }
        ],
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert result.ok, result.summary()


def test_file_list_size_limit() -> None:
    files = [{"name": f"f{i}.txt"} for i in range(MAX_FILE_ITEMS + 1)]
    surface = _root_only(["f"], rest=[{"id": "f", "component": "FileList", "files": files}])
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert str(MAX_FILE_ITEMS) in result.summary()


@pytest.mark.parametrize("bad", ["/etc/passwd", "../../secret.txt"])
def test_file_list_rejects_unsafe_path(bad: str) -> None:
    surface = _root_only(
        ["f"], rest=[{"id": "f", "component": "FileList", "files": [{"name": "x", "path": bad}]}]
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert ".." in result.summary() or "绝对路径" in result.summary()


def test_file_list_rejects_unknown_field_and_missing_name() -> None:
    surface = _root_only(
        ["f"],
        rest=[{"id": "f", "component": "FileList", "files": [{"name": "a", "mime": "x/y"}]}],
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert not result.ok
    assert "mime" in result.summary()

    missing = _root_only(
        ["f"], rest=[{"id": "f", "component": "FileList", "files": [{"path": "a.txt"}]}]
    )
    assert not validate_ui_surface(missing, catalog_id=CATALOG_ID).ok


def test_rich_media_components_are_in_catalog() -> None:
    """S5 的目录扩到 21 个组件，且富媒体组独立成组。"""
    doc = catalog_document()
    assert len(doc["components"]) == 21
    assert doc["groups"]["media"] == "富媒体"
    for name in ("Chart", "Graph", "FileList"):
        assert doc["components"][name]["group"] == "media"


# --------------------------------------------------------------------------
# 告警路径
# --------------------------------------------------------------------------


def test_unreachable_component_warned_and_pruned() -> None:
    surface = _root_only(
        ["a"],
        rest=[
            {"id": "a", "component": "Text", "text": "可见"},
            {"id": "orphan", "component": "Text", "text": "谁也够不到"},
        ],
    )
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert result.ok, result.summary()
    assert any("不可达" in w.message for w in result.warnings)
    ids = [c["id"] for c in (result.normalized or {})["components"]]
    assert "orphan" not in ids and "a" in ids


def test_builtin_action_in_declaration_warns() -> None:
    surface = _root_only(
        ["btn"],
        rest=[{"id": "btn", "component": "Button", "text": "提交",
               "action": {"name": "submit"}}],
    )
    surface["actions"] = ["submit"]
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert result.ok
    assert any("内置动作" in w.message for w in result.warnings)


# --------------------------------------------------------------------------
# 版本边界：v0.9.1 消息信封快照
# --------------------------------------------------------------------------


def test_messages_envelope_snapshot() -> None:
    surface = _root_only(
        ["t", "btn"],
        rest=[
            {"id": "t", "component": "Text", "text": {"path": "/msg"}},
            {"id": "btn", "component": "Button", "text": "算",
             "action": {"name": "recalc", "context": [{"key": "k", "value": 1}]}},
        ],
        data={"msg": "hi"},
    )
    surface["actions"] = ["recalc"]
    result = validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert result.ok, result.summary()
    messages = to_messages(result.normalized or {})

    assert messages[0] == {
        "version": A2UI_VERSION,
        "createSurface": {"surfaceId": "s1", "catalogId": CATALOG_ID},
    }
    assert messages[1]["updateComponents"]["surfaceId"] == "s1"
    button = next(
        c for c in messages[1]["updateComponents"]["components"] if c["id"] == "btn"
    )
    # action 必须换成 v0.9.1 的 envelope 形态，而不是原样透传 IR
    assert button["action"] == {
        "event": {"name": "recalc", "context": [{"key": "k", "value": 1}]}
    }
    assert messages[2] == {
        "version": A2UI_VERSION,
        "updateDataModel": {"surfaceId": "s1", "path": "/", "value": {"msg": "hi"}},
    }


def test_sse_payload_shape() -> None:
    result = validate_ui_surface(sample_surface(), catalog_id=CATALOG_ID)
    payload = to_sse_payload(result.normalized or {}, seq=3, source_call_id="call_1")
    assert payload["event"] == "a2ui"
    assert payload["surfaceId"] == "cost-panel"
    assert payload["seq"] == 3
    assert payload["source_call_id"] == "call_1"
    assert len(payload["messages"]) >= 2
    # 帧内完整性：所有消息都带 version，且没有 None
    assert all(m.get("version") == A2UI_VERSION for m in payload["messages"])


def test_validator_does_not_mutate_input() -> None:
    surface = sample_surface()
    before = copy.deepcopy(surface)
    validate_ui_surface(surface, catalog_id=CATALOG_ID)
    assert surface == before


# --------------------------------------------------------------------------
# 契约产物漂移守卫（照 test_render_graph.py 的做法）
# --------------------------------------------------------------------------


def test_catalog_artifact_matches_source() -> None:
    """`divine_catalog.json` 是签入产物；它必须等于 catalog.py 生成的结果。

    改了 catalog.py 却忘了同步产物 → 前端镜像与后端真源会悄悄分叉。
    """
    on_disk = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    assert on_disk == catalog_document()


# --------------------------------------------------------------------------
# 适配器接线（render_ui）
# --------------------------------------------------------------------------


def _adapter():
    from app.tools.registry import registry

    adapter = registry.get("render_ui")
    assert adapter is not None, "render_ui 必须已注册（adapters/__init__ 静态导入）"
    return adapter


def _run(arguments: dict) -> object:
    return asyncio.run(_adapter().run(Path("."), arguments))


def test_render_ui_is_registered_and_read_only() -> None:
    from app.agent.core.constants import _READ_ONLY_TOOLS

    assert _adapter() is not None
    # 纯展示工具：无 IO、无副作用 → 免审批、免锁、plan_first 期间放行
    assert "render_ui" in _READ_ONLY_TOOLS


def test_adapter_returns_surface_and_messages() -> None:
    from app.tools.base import ToolResult

    result = _run(sample_surface())
    assert isinstance(result, ToolResult) and result.success
    data = result.data or {}
    assert data["surfaceId"] == "cost-panel"
    assert data["actionNames"] == ["recalc", "export_pdf"]
    assert len(data["a2uiMessages"]) >= 2
    # 模型只看到规模摘要，不看回完整 JSON
    content = json.loads(result.content)
    assert content["components"] == 10
    assert content["surfaceId"] == "cost-panel"


def test_adapter_accepts_nested_surface_alias() -> None:
    result = _run({"surface": sample_surface()})
    assert result.success


def test_adapter_rejects_invalid_surface() -> None:
    from app.tools.base import ToolExecutionError

    with pytest.raises(ToolExecutionError) as excinfo:
        _run({"surfaceId": "s1", "components": [{"id": "x", "component": "Nope"}]})
    assert "Nope" in str(excinfo.value)


def test_adapter_rejects_unknown_argument() -> None:
    from app.tools.base import ToolExecutionError

    with pytest.raises(ToolExecutionError) as excinfo:
        _run({**sample_surface(), "color_scheme": "teal"})
    assert "color_scheme" in str(excinfo.value)


def test_adapter_does_not_mutate_arguments() -> None:
    surface = sample_surface()
    before = copy.deepcopy(surface)
    _run(surface)
    assert surface == before


# --------------------------------------------------------------------------
# 执行层：a2ui 事件载荷
# --------------------------------------------------------------------------


def test_take_a2ui_payload_builds_event_and_strips_messages() -> None:
    from app.agent.tools.execution import _take_a2ui_payload

    output = {
        "success": True,
        "data": {
            "surfaceId": "cost-panel",
            "uiSurface": {"surfaceId": "cost-panel"},
            "a2uiMessages": [{"version": A2UI_VERSION, "createSurface": {}}],
        },
    }
    payload = _take_a2ui_payload(output, "call_1", 2)
    assert payload == {
        "event": "a2ui",
        "surfaceId": "cost-panel",
        "seq": 2,
        "source_call_id": "call_1",
        "messages": [{"version": A2UI_VERSION, "createSurface": {}}],
    }
    # 消息已摘除：只走事件，不随 tool result 再传一份
    assert "a2uiMessages" not in output["data"]
    # 兜底用的 IR 仍在
    assert output["data"]["uiSurface"] == {"surfaceId": "cost-panel"}


@pytest.mark.parametrize(
    "output",
    [{}, {"data": None}, {"data": {}}, {"data": {"a2uiMessages": []}}],
)
def test_take_a2ui_payload_returns_none(output: dict) -> None:
    from app.agent.tools.execution import _take_a2ui_payload

    assert _take_a2ui_payload(dict(output), "c", 1) is None


def test_ui_surface_is_opaque_to_frontend_truncation() -> None:
    """漏掉这个 opaque key 的表现是「面板少了几个组件」且不报错（044 §5.3）。"""
    from app.agent.state.persistence import (
        _FRONTEND_OPAQUE_KEYS,
        _frontend_tool_result,
    )

    assert "uiSurface" in _FRONTEND_OPAQUE_KEYS
    big = {"components": [{"id": f"c{i}"} for i in range(80)], "longlist": [1] * 60}
    out = _frontend_tool_result({"data": {"uiSurface": big}})
    # 组件与列表都不被截断
    assert len(out["data"]["uiSurface"]["components"]) == 80
    assert len(out["data"]["uiSurface"]["longlist"]) == 60


# --------------------------------------------------------------------------
# 开关
# --------------------------------------------------------------------------


def test_flag_gates_render_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agent.tools import tools as tools_mod

    monkeypatch.setattr(tools_mod.settings_store, "load", lambda: {})
    assert tools_mod._ui_a2ui_enabled() is False  # 默认关闭

    monkeypatch.setattr(
        tools_mod.settings_store, "load", lambda: {"ui_a2ui_enabled": True}
    )
    assert tools_mod._ui_a2ui_enabled() is True


def test_flag_defaults_off_in_config() -> None:
    from app.config import SettingsStore

    # 不读磁盘，只看 _build() 的默认值
    assert SettingsStore()._build().get("ui_a2ui_enabled") is False


# --------------------------------------------------------------------------
# 提示词节与工具可见性「同源」（028 §10.1 ③）
# --------------------------------------------------------------------------


def test_a2ui_intents_are_the_single_criterion() -> None:
    """三个消费方必须用同一份 A2UI_INTENTS，否则会「提示词说了工具没挂」或反之。"""
    from app.agent.core import A2UI_INTENTS
    from app.agent.core.prompt_sections import _A2UI_SECTION
    from app.agent.intent.intent import CONDITIONAL_SECTIONS, _INTENT_ORDER
    from app.agent.tools.tools import _CONTENT_TOOLS

    assert A2UI_INTENTS, "判据不能为空"
    # ① 工具可见性用的是同一份集合
    assert tuple(_CONTENT_TOOLS["render_ui"]) == tuple(A2UI_INTENTS)
    # ② 提示词节挂在同样的每个意图上
    for intent in A2UI_INTENTS:
        assert intent in CONDITIONAL_SECTIONS, f"{intent} 没有条件节"
        assert _A2UI_SECTION in CONDITIONAL_SECTIONS[intent]
    # ③ 每个意图都在输出顺序表里（否则节永远发不出来）
    for intent in A2UI_INTENTS:
        assert intent in _INTENT_ORDER


def test_a2ui_section_is_a_cheat_sheet() -> None:
    """§10.1 ②：提示词节只能是 ≤12 行 cheat-sheet（重复 schema 会污染前缀缓存）。"""
    from app.agent.core.prompt_sections import _A2UI_SECTION

    assert len(_A2UI_SECTION.strip().splitlines()) <= 12


def test_a2ui_section_only_for_matching_intents() -> None:
    from app.agent.intent.intent import build_rule_sections

    assert "交互面板 render_ui" in build_rule_sections({"chart"}, is_first_turn=False)
    # 闲聊/记忆类意图不该空载这块规则
    assert "交互面板 render_ui" not in build_rule_sections(
        {"memory"}, is_first_turn=False
    )
    # 首轮且无意图时注入完整 SYSTEM_PROMPT（保守兜底），本就不含条件节
    assert "交互面板 render_ui" not in build_rule_sections(set(), is_first_turn=True)


def test_render_ui_tool_visibility_follows_intents() -> None:
    from app.agent.tools.tools import _content_tool_allowed

    assert _content_tool_allowed("render_ui", {"chart"}) is True
    assert _content_tool_allowed("render_ui", {"document"}) is True
    # 与「呈现/交互」无关的意图命中时工具下线
    assert _content_tool_allowed("render_ui", {"memory"}) is False
    assert _content_tool_allowed("render_ui", {"terminal"}) is False
    # 无信号（空意图）时全量放行：追问轮不会「该用用不了」
    assert _content_tool_allowed("render_ui", set()) is True

