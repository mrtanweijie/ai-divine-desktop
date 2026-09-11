"""Tests for render_graph — GraphIR contract, validator and tool wiring.

Covers the checklist in docs/design/020-x6-multi-scenario-20260908.md §3:
enum closure, coordinate/colour ban, whitelist-only keys, reference integrity,
scenario-specific rules (2b–2h), size limits and structured error reporting.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.tools.adapters.render_graph import RenderGraphAdapter
from app.tools.graph import schema as S
from app.tools.graph.validator import validate_graph_ir
from app.tools.registry import get_tool

SCHEMA_FILE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "tools"
    / "graph"
    / "graph_ir.schema.json"
)


def _run(ir: dict) -> object:
    tool = get_tool("render_graph")
    assert tool is not None
    return asyncio.run(tool.run(Path("."), ir))


def _errors(ir: dict) -> str:
    """Run the tool expecting rejection; return the structured report."""
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 — ToolExecutionError
        _run(ir)
    return str(excinfo.value)


def _flow(nodes: int = 3, edges: int = 2) -> dict:
    return {
        "kind": "flow",
        "title": "订单链路",
        "nodes": [{"id": f"n{i}", "label": f"步骤 {i}"} for i in range(nodes)],
        "edges": [{"source": f"n{i}", "target": f"n{i + 1}"} for i in range(edges)],
    }


# --------------------------------------------------------------------------
# Tool registration & description (routing is prompt-level behaviour)
# --------------------------------------------------------------------------
def test_tool_is_registered_under_diagrams():
    tool = get_tool("render_graph")
    assert tool is not None
    assert tool.category == "diagrams"
    assert tool.parameters["required"] == ["kind", "nodes"]


def test_kind_enum_matches_contract():
    tool = get_tool("render_graph")
    assert tool.parameters["properties"]["kind"]["enum"] == list(S.GRAPH_KINDS)
    assert len(S.GRAPH_KINDS) == 15


def test_description_enforces_two_stage_routing():
    """Mermaid first; render_graph only on an explicit interaction request."""
    tool = get_tool("render_graph")
    description = tool.description
    assert "默认不要调用本工具" in description
    assert "交互" in description and "导出" in description
    # every scenario is discoverable from the description alone
    for kind in S.GRAPH_KINDS:
        assert kind in description
    # the hard bans are spelled out, not implied
    assert "禁止任何坐标" in description
    assert "禁止 URL" in description


def test_no_streaming_in_tool_contract():
    """004 决策 13 — the tool returns the whole IR, never incremental events."""
    tool = get_tool("render_graph")
    assert "stream" not in json.dumps(tool.parameters).lower()


# --------------------------------------------------------------------------
# Happy path & normalisation
# --------------------------------------------------------------------------
def test_valid_flow_returns_full_ir_for_the_frontend():
    result = _run(
        {
            "kind": "flow",
            "title": "订单支付链路",
            "nodes": [
                {"id": "user", "label": "提交订单", "role": "start"},
                {"id": "pay", "label": "发起支付", "role": "process", "tone": "info"},
            ],
            "edges": [
                {"source": "user", "target": "pay", "flow": {"mode": "antline", "speed": 1}}
            ],
            "demoPath": ["user", "pay"],
        }
    )
    assert result.success is True
    ir = result.data["graphIR"]
    assert ir["kind"] == "flow"
    assert ir["meta"]["title"] == "订单支付链路"
    assert len(ir["nodes"]) == 2
    # edge ids are stabilised so persistence and diffing stay deterministic
    assert ir["edges"][0]["id"] == "e1"
    assert result.data["spec_version"] == 1


def test_model_payload_stays_small():
    """The model wrote the IR — echoing it back burns context for nothing."""
    payload = json.loads(_run(_flow()).content)
    assert payload["success"] is True
    assert set(payload) == {"success", "message", "kind", "nodes", "edges"}


def test_graph_alias_is_accepted():
    result = _run({"graph": _flow(), "title": "别名入口"})
    assert result.data["graphIR"]["meta"]["title"] == "别名入口"


# --------------------------------------------------------------------------
# Enum closure — no silent fallback (004 决策 2)
# --------------------------------------------------------------------------
def test_unknown_kind_is_rejected_never_downgraded():
    report = _errors({**_flow(), "kind": "flowchart"})
    assert "未知场景" in report
    for kind in S.GRAPH_KINDS:
        assert kind in report


def test_missing_kind_is_rejected():
    ir = _flow()
    del ir["kind"]
    assert "缺少 kind" in _errors(ir)


def test_unknown_role_is_rejected():
    ir = _flow()
    ir["nodes"][0]["role"] = "step"
    report = _errors(ir)
    assert "语义角色" in report and "process" in report


def test_unknown_tone_is_rejected():
    ir = _flow()
    ir["nodes"][0]["tone"] = "primary"
    assert "tone 取值" in _errors(ir)


# --------------------------------------------------------------------------
# Geometry / colour / visual hints are not the model's business
# --------------------------------------------------------------------------
@pytest.mark.parametrize("key", ["x", "y", "w", "h", "pos", "size", "via", "fromSide"])
def test_coordinate_fields_are_rejected(key):
    ir = _flow()
    ir["nodes"][0][key] = 120
    assert "禁止坐标/尺寸字段" in _errors(ir)


@pytest.mark.parametrize("key", ["bc", "shape", "direction", "layout"])
def test_visual_hint_fields_are_rejected(key):
    ir = _flow()
    ir["edges"][0][key] = 0
    assert "禁止" in _errors(ir)


@pytest.mark.parametrize("value", ["#DD656D", "#fff", "rgb(1,2,3)"])
def test_colour_literals_are_rejected(value):
    ir = _flow()
    ir["nodes"][0]["tone"] = value
    report = _errors(ir)
    assert "禁止色值字面量" in report
    # the colour report is enough — no duplicate "illegal value" noise
    assert report.count("$.nodes[0].tone") == 1


# --------------------------------------------------------------------------
# Whitelist only
# --------------------------------------------------------------------------
def test_unknown_keys_are_rejected_at_every_level():
    ir = _flow()
    ir["mystery"] = 1
    assert "不认识的字段" in _errors(ir)

    ir = _flow()
    ir["nodes"][0]["color"] = "red"
    assert "禁止色值字段" in _errors(ir)

    ir = _flow()
    ir["edges"][0]["svgAttrs"] = {"fill": "red"}
    assert "不认识的字段" in _errors(ir)


@pytest.mark.parametrize("key", ["__proto__", "constructor", "prototype", "onClick"])
def test_prototype_and_handler_injection_is_rejected(key):
    ir = _flow()
    ir["nodes"][0][key] = {"polluted": True}
    assert "禁止" in _errors(ir)


def test_unknown_top_level_argument_is_rejected():
    report = _errors({**_flow(), "options": {}})
    assert "不认识的字段" in report
    assert "allowed" not in report  # message stays Chinese


# --------------------------------------------------------------------------
# Identity & references
# --------------------------------------------------------------------------
def test_duplicate_node_id_is_rejected():
    ir = _flow()
    ir["nodes"][1]["id"] = "n0"
    assert "id 重复" in _errors(ir)


def test_node_id_format_is_enforced():
    ir = _flow()
    ir["nodes"][0]["id"] = "bad id!"
    assert "非法节点 id" in _errors(ir)


@pytest.mark.parametrize("field", ["source", "target"])
def test_edge_endpoints_must_exist(field):
    ir = _flow()
    ir["edges"][0][field] = "ghost"
    assert "不是已声明的节点 id" in _errors(ir)


def test_group_members_must_exist():
    ir = _flow()
    ir["groups"] = [{"id": "g1", "label": "层", "type": "cluster", "members": ["ghost"]}]
    assert "不是已声明的节点 id" in _errors(ir)


def test_demo_path_must_reference_nodes():
    ir = _flow()
    ir["demoPath"] = ["n0", "ghost"]
    assert "$.demoPath[1]" in _errors(ir)


# --------------------------------------------------------------------------
# Scenario-specific rules (2b–2h)
# --------------------------------------------------------------------------
def test_icon_whitelist_rejects_urls():
    ir = _flow()
    ir["kind"] = "dag"
    ir["nodes"][0]["icon"] = "https://cdn.example.com/icon.svg"
    report = _errors(ir)
    assert "非法图标" in report and "禁止 URL" in report


def test_icon_accepts_inline_names_only():
    ir = _flow()
    ir["kind"] = "dag"
    ir["nodes"][0]["icon"] = "flask"
    ir["nodes"][0]["state"] = "running"
    assert _run(ir).success is True


def test_active_flag_is_unique_across_the_graph():
    ir = {
        "kind": "state",
        "nodes": [
            {"id": "a", "label": "待支付", "active": True},
            {"id": "b", "label": "已支付", "active": True},
        ],
        "edges": [{"source": "a", "target": "b"}],
    }
    assert "只能有一个当前激活状态" in _errors(ir)


def test_pseudo_state_needs_no_label():
    ir = {
        "kind": "state",
        "nodes": [{"id": "init", "pseudo": "initial"}, {"id": "done", "label": "已完成"}],
        "edges": [{"source": "init", "target": "done"}],
    }
    assert _run(ir).success is True


def test_pseudo_state_enum_is_closed():
    ir = {
        "kind": "state",
        "nodes": [{"id": "a", "pseudo": "beginning"}],
        "edges": [],
    }
    assert "伪状态取值" in _errors(ir)


def test_boundary_depth_is_capped_at_two():
    ir = {
        "kind": "arch",
        "nodes": [{"id": "a", "label": "API", "type": "backend"}],
        "edges": [],
        "groups": [
            {"id": "r", "type": "region", "label": "R", "members": ["a"]},
            {"id": "v", "type": "vpc", "label": "V", "members": ["a"]},
            {"id": "s", "type": "security-group", "label": "S", "members": ["a"]},
        ],
    }
    report = _errors(ir)
    assert "被 3 层边界包裹" in report
    assert "上限 2 层" in report


def test_two_boundary_layers_are_accepted():
    ir = {
        "kind": "arch",
        "nodes": [{"id": "lb", "label": "负载均衡", "type": "cloud"},
                  {"id": "api", "label": "API 服务", "type": "backend",
                   "sublabel": "FastAPI :8000", "tag": "OAI"}],
        "edges": [{"source": "lb", "target": "api"}],
        "groups": [
            {"id": "region", "kind": "region", "label": "AWS Region",
             "wraps": ["lb", "api"]},
            {"id": "sg", "kind": "security-group", "label": "sg-api",
             "wraps": ["lb", "api"]},
        ],
    }
    result = _run(ir)
    assert result.success is True
    # group `kind`/`wraps` aliases fold into `type`/`members` for the frontend
    groups = result.data["graphIR"]["groups"]
    assert groups[0] == {"id": "region", "label": "AWS Region", "type": "region",
                         "members": ["lb", "api"]}


def test_arch_type_enum_is_scenario_scoped():
    ir = {
        "kind": "arch",
        "nodes": [{"id": "a", "label": "A", "type": "module"}],
        "edges": [],
    }
    assert "不是 arch 角色" in _errors(ir)


def test_concept_type_enum_is_scenario_scoped():
    ir = {
        "kind": "concept",
        "nodes": [{"id": "a", "label": "A", "type": "backend"}],
        "edges": [],
    }
    assert "不是 concept 类型" in _errors(ir)


def test_swimlane_requires_lane_groups_and_assignment():
    ir = {
        "kind": "swimlane",
        "nodes": [{"id": "a", "label": "A", "lane": "l1"}, {"id": "b", "label": "B"}],
        "edges": [{"source": "a", "target": "b"}],
    }
    report = _errors(ir)
    assert "需要声明泳道" in report
    assert "缺少 lane" in report


def test_swimlane_happy_path():
    ir = {
        "kind": "swimlane",
        "nodes": [{"id": "a", "label": "A", "lane": "l1"},
                  {"id": "b", "label": "B", "lane": "l2"}],
        "edges": [{"source": "a", "target": "b"}],
        "groups": [
            {"id": "l1", "label": "用户", "type": "lane", "members": ["a"]},
            {"id": "l2", "label": "后台", "type": "lane", "members": ["b"]},
        ],
    }
    assert _run(ir).success is True


def test_sequence_rejects_cycles():
    ir = {
        "kind": "sequence",
        "nodes": [{"id": "a", "label": "客户端"}, {"id": "b", "label": "服务"}],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
    }
    assert "出现环" in _errors(ir)


def test_sequence_participant_limit():
    ir = {
        "kind": "sequence",
        "nodes": [{"id": f"p{i}", "label": f"参与者 {i}"}
                  for i in range(S.NODE_LIMITS["sequence"] + 1)],
        "edges": [],
    }
    report = _errors(ir)
    assert "超过 sequence 上限" in report


def test_state_guard_label_length_is_capped():
    ir = {
        "kind": "state",
        "nodes": [{"id": "a", "label": "待支付"}, {"id": "b", "label": "已支付"}],
        "edges": [
            {"source": "a", "target": "b",
             "label": "超时 [" + "x" * (S.MAX_GUARD_LEN + 5) + "]"},
        ],
    }
    assert "守卫条件长度" in _errors(ir)


def test_state_guard_label_is_accepted():
    ir = {
        "kind": "state",
        "nodes": [{"id": "a", "label": "待支付"}, {"id": "b", "label": "已支付"}],
        "edges": [{"source": "a", "target": "b", "label": "超时 [未支付]"}],
    }
    assert _run(ir).success is True


# --------------------------------------------------------------------------
# Size limits
# --------------------------------------------------------------------------
def test_node_limit_is_per_scenario():
    over = S.NODE_LIMITS["er"] + 1
    ir = {
        "kind": "er",
        "nodes": [{"id": f"t{i}", "label": f"表 {i}"} for i in range(over)],
        "edges": [],
    }
    assert "超过 er 上限" in _errors(ir)


def test_flow_allows_more_nodes_than_er():
    ir = {
        "kind": "flow",
        "nodes": [{"id": f"n{i}", "label": f"节点 {i}"} for i in range(40)],
        "edges": [{"source": f"n{i}", "target": f"n{i + 1}"} for i in range(39)],
    }
    assert _run(ir).success is True


def test_label_length_is_capped():
    ir = _flow()
    ir["nodes"][0]["label"] = "长" * (S.MAX_LABEL_LEN + 1)
    assert "超过上限" in _errors(ir)


# --------------------------------------------------------------------------
# Warnings do not block
# --------------------------------------------------------------------------
def test_sixth_category_warns_but_renders():
    ir = {
        "kind": "arch",
        "nodes": [
            {"id": f"n{i}", "label": f"服务 {i}", "type": "backend", "category": f"类别{i}"}
            for i in range(S.MAX_CATEGORIES + 1)
        ],
        "edges": [],
    }
    result = _run(ir)
    assert result.success is True
    assert "第 6 类起不着色" in result.message


def test_unused_scenario_field_warns_only():
    ir = _flow()
    ir["nodes"][0]["icon"] = "JOIN"  # 加工类型图标只在 dataflow/dag 生效
    result = _run(ir)
    assert result.success is True
    assert "已忽略" in result.message


# --------------------------------------------------------------------------
# Contract artefact & payload transport
# --------------------------------------------------------------------------
def test_schema_file_stays_in_sync_with_code():
    """The checked-in JSON Schema is the cross-implementation contract."""
    on_disk = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    assert on_disk == S.json_schema()


def test_graph_payload_survives_frontend_truncation():
    """data.graphIR must reach the WebView intact (no 50-item list cap)."""
    from app.agent.state.persistence import _frontend_tool_result

    payload = {
        "success": True,
        "message": "ok",
        "data": {"graphIR": _flow(nodes=60, edges=59)},
    }
    forwarded = _frontend_tool_result(payload)
    assert len(forwarded["data"]["graphIR"]["nodes"]) == 60
    assert len(forwarded["data"]["graphIR"]["edges"]) == 59
    # everything else keeps the historical guard rails
    big = {"data": {"results": list(range(80))}}
    assert len(_frontend_tool_result(big)["data"]["results"]) == 13


def test_validator_exposes_rejection_for_direct_use():
    """The validator is usable without the adapter (frontend parity tests)."""
    outcome = validate_graph_ir({"kind": "nope", "nodes": []})
    assert outcome.ok is False
    assert outcome.normalized is None
    assert any(issue.path == "$.kind" for issue in outcome.issues)
