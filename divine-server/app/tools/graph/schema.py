"""GraphIR contract — closed enums, per-scenario limits and the JSON Schema.

Single source of truth for the backend side of the *interactive graph* pipeline
(design doc: ``docs/design/020-x6-multi-scenario-20260908.md`` §3 / §4 / §5).

Why this module exists
----------------------
The IR is produced by the LLM and consumed by two independent implementations
(Python validator here, TypeScript mirror in ``divine-app/.../GraphBlock/GraphIR.ts``).
Keeping the enums in one place — and *generating* ``graph_ir.schema.json`` from
them — is what stops the two sides from drifting.

Design principle (004 决策 1): the IR carries **what to draw**, never **how**.
No coordinates, no colours, no shapes, no layout hints. Anything visual is
resolved by the frontend ScenarioPreset table.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------
# Scenario enum — the only scenario field in the IR (15 closed values)
# --------------------------------------------------------------------------
GRAPH_KINDS: tuple[str, ...] = (
    "flow",
    "dag",
    "dataflow",
    "state",
    "org",
    "mindmap",
    "topology",
    "arch",
    "er",
    "swimlane",
    "sequence",
    "concept",
    "class",
    "fishbone",
    "timeline",
)

#: Human readable scenario names — used in error hints so the Agent can pick
#: the right kind without a second round-trip.
KIND_LABELS: dict[str, str] = {
    "flow": "业务流程 / 决策流",
    "dag": "任务编排 DAG",
    "dataflow": "数据加工 DAG",
    "state": "状态机",
    "org": "组织架构 / 层级树",
    "mindmap": "思维导图",
    "topology": "系统 / 网络拓扑",
    "arch": "系统架构图",
    "er": "实体关系",
    "swimlane": "跨职能流程 / 泳道",
    "sequence": "异步任务往返时序",
    "concept": "知识图谱 / 关系网",
    "class": "UML 类图",
    "fishbone": "鱼骨 / 因果",
    "timeline": "时间线 / 里程碑",
}

#: Per-scenario node ceiling (004 决策 4) — mirrored in the frontend Preset table
#: ``presets.ts``; P0 frame-rate measurements may revise both in lockstep.
NODE_LIMITS: dict[str, int] = {
    "flow": 80,
    "dag": 120,
    "dataflow": 80,
    "state": 40,
    "org": 150,
    "mindmap": 120,
    "topology": 100,
    "er": 24,
    "swimlane": 60,
    "sequence": 12,  # 参与者（时序语义上限，见 SEQUENCE_MESSAGE_LIMIT）
    "arch": 60,
    "concept": 80,
    "class": 20,
    "fishbone": 40,
    "timeline": 30,
}

#: Sequence is the only scenario with an explicit message ceiling (§3 校验 2h).
SEQUENCE_MESSAGE_LIMIT = 24

#: Fallback edge ceiling for every other scenario (sanity guard, not a design
#: limit — keeps a runaway payload from reaching the layout engine).
EDGE_LIMIT_FACTOR = 3

# --------------------------------------------------------------------------
# Node / edge enums
# --------------------------------------------------------------------------
NODE_ROLES: tuple[str, ...] = (
    "start",
    "end",
    "process",
    "decision",
    "data",
    "entity",
    "state",
    "milestone",
    "member",
)

TONES: tuple[str, ...] = ("neutral", "info", "success", "warning", "error")

#: dag / dataflow execution state — mapped onto tone by the frontend,
#: never a second colour system (020 §5.5).
NODE_STATES: tuple[str, ...] = ("pending", "running", "success", "failed")

STATE_TONE_MAP: dict[str, str] = {
    "pending": "neutral",
    "running": "info",
    "success": "success",
    "failed": "error",
}

#: 8 task icons (dag) — inlined SVG paths on the frontend, no URLs ever.
TASK_ICONS: tuple[str, ...] = (
    "code",
    "box",
    "check",
    "flask",
    "stack",
    "layers",
    "upload",
    "gear",
)

#: 6 data-processing types (dataflow) — rendered as the icon tile.
FLOW_ICONS: tuple[str, ...] = ("INPUT", "FILTER", "JOIN", "UNION", "AGG", "OUTPUT")

#: Combined whitelist for ``node.icon`` (validator rule 2b).
NODE_ICONS: tuple[str, ...] = TASK_ICONS + FLOW_ICONS

#: UML pseudo states (state) — circles are reserved for these in UML.
PSEUDO_STATES: tuple[str, ...] = ("initial", "final", "choice")

#: concept node types — icon inside the circle.
CONCEPT_TYPES: tuple[str, ...] = ("module", "tech", "data", "process", "concept")

#: arch node roles — icon tile.
ARCH_TYPES: tuple[str, ...] = (
    "external",
    "security",
    "cloud",
    "backend",
    "database",
    "messagebus",
)

#: group / container types. ``lane`` and ``cluster`` come from §5.4; the three
#: boundary types come from §5.7 (arch, overlap-drawn instead of nested).
GROUP_TYPES: tuple[str, ...] = (
    "lane",
    "cluster",
    "combo",
    "region",
    "vpc",
    "security-group",
)

#: Boundary types are drawn as nested-looking overlapping boxes — max depth 2.
BOUNDARY_TYPES: tuple[str, ...] = ("region", "vpc", "security-group")
MAX_BOUNDARY_DEPTH = 2

#: Category colouring (020 §5.9): the Agent supplies a *name*, never a colour.
MAX_CATEGORIES = 5

EDGE_KINDS: tuple[str, ...] = (
    "flow",
    "dep",
    "transit",
    "inherit",
    "assoc",
    "contain",
)
EDGE_STYLES: tuple[str, ...] = ("solid", "dashed", "dotted")
FLOW_MODES: tuple[str, ...] = ("antline", "pulse")
FLOW_SPEEDS: tuple[float, ...] = (0.5, 1.0, 2.0)

# --------------------------------------------------------------------------
# Field whitelists — IR comes from the LLM and is treated as untrusted input.
# Unknown keys are rejected (no silent passthrough of arbitrary SVG attrs).
# --------------------------------------------------------------------------
TOP_KEYS: tuple[str, ...] = (
    "kind",
    "meta",
    "nodes",
    "edges",
    "groups",
    "demoPath",
)
META_KEYS: tuple[str, ...] = ("title", "summary")
NODE_KEYS: tuple[str, ...] = (
    "id",
    "label",
    "role",
    "tone",
    "note",
    "badge",
    # scenario-specific optional fields (Preset declares support, others ignore)
    "state",
    "icon",
    "pseudo",
    "active",
    "role_desc",
    "count",
    "type",
    "category",
    "sublabel",
    "tag",
    "lane",
    "parent",
)
EDGE_KEYS: tuple[str, ...] = (
    "id",
    "source",
    "target",
    "label",
    "kind",
    "tone",
    "style",
    "flow",
)
GROUP_KEYS: tuple[str, ...] = ("id", "label", "type", "members", "kind", "wraps")

#: Explicitly banned keys. Coordinates and colours are the two things the Agent
#: must never send (004 决策 1 / 020 §3 校验 6); ``bc`` is assigned by the
#: frontend per branch order.
FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "x",
        "y",
        "w",
        "h",
        "width",
        "height",
        "pos",
        "position",
        "size",
        "via",
        "fromSide",
        "toSide",
        "coords",
        "coordinates",
        "bc",
        "color",
        "colour",
        "fill",
        "stroke",
        "backgroundColor",
        "direction",
        "shape",
        "layout",
    }
)

#: Prototype-pollution / handler-injection keys.
DANGEROUS_KEYS: frozenset[str] = frozenset({"__proto__", "constructor", "prototype"})

# --------------------------------------------------------------------------
# Length / format guards
# --------------------------------------------------------------------------
ID_PATTERN = r"^[A-Za-z0-9_\-.:]{1,64}$"
MAX_LABEL_LEN = 60
MAX_GUARD_LEN = 24
MAX_NOTE_LEN = 500
MAX_BADGE_LEN = 12
MAX_TITLE_LEN = 60
MAX_SUMMARY_LEN = 240
MAX_SUBLABEL_LEN = 40
MAX_TAG_LEN = 16
MAX_ROLE_DESC_LEN = 40
MAX_CATEGORY_LEN = 20
MAX_DEMO_PATH_LEN = 60

#: Any colour literal is rejected wherever it appears (§3 校验 3).
COLOUR_LITERAL_PATTERN = (
    r"(^#(?:[0-9a-fA-F]{3,8})$)"
    r"|(^rgba?\s*\()"
    r"|(^hsla?\s*\()"
    r"|(^[a-zA-Z]+\s*$)"  # bare CSS colour words are not caught here on purpose
)


def node_limit(kind: str) -> int:
    """Node ceiling for ``kind`` (falls back to the smallest tier)."""
    return NODE_LIMITS.get(kind, 24)


def edge_limit(kind: str) -> int:
    """Edge ceiling for ``kind`` — explicit for sequence, derived otherwise."""
    if kind == "sequence":
        return SEQUENCE_MESSAGE_LIMIT
    return node_limit(kind) * EDGE_LIMIT_FACTOR


def json_schema() -> dict[str, Any]:
    """Machine-readable GraphIR schema (the cross-implementation contract).

    Kept deliberately permissive about *cross-field* rules (reference integrity,
    ``active`` uniqueness, boundary depth) — those live in :mod:`.validator` and
    cannot be expressed in JSON Schema without a resolver.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://divine.local/schemas/graph-ir.schema.json",
        "title": "GraphIR",
        "description": (
            "Declarative graph description for the render_graph tool. Carries "
            "topology and semantics only: no coordinates, no colours, no shapes."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "nodes"],
        "properties": {
            "kind": {"enum": list(GRAPH_KINDS)},
            "meta": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string", "maxLength": MAX_TITLE_LEN},
                    "summary": {"type": "string", "maxLength": MAX_SUMMARY_LEN},
                },
            },
            "nodes": {
                "type": "array",
                "minItems": 1,
                "maxItems": max(NODE_LIMITS.values()),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string", "pattern": ID_PATTERN},
                        "label": {"type": "string", "maxLength": MAX_LABEL_LEN},
                        "role": {"enum": list(NODE_ROLES)},
                        "tone": {"enum": list(TONES)},
                        "note": {"type": "string", "maxLength": MAX_NOTE_LEN},
                        "badge": {"type": "string", "maxLength": MAX_BADGE_LEN},
                        "state": {"enum": list(NODE_STATES)},
                        "icon": {"enum": list(NODE_ICONS)},
                        "pseudo": {"enum": list(PSEUDO_STATES)},
                        "active": {"type": "boolean"},
                        "role_desc": {"type": "string", "maxLength": MAX_ROLE_DESC_LEN},
                        "count": {"type": "integer", "minimum": 0},
                        "type": {"enum": list(CONCEPT_TYPES + ARCH_TYPES)},
                        "category": {"type": "string", "maxLength": MAX_CATEGORY_LEN},
                        "sublabel": {"type": "string", "maxLength": MAX_SUBLABEL_LEN},
                        "tag": {"type": "string", "maxLength": MAX_TAG_LEN},
                        "lane": {"type": "string"},
                        "parent": {"type": "string"},
                    },
                },
            },
            "edges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["source", "target"],
                    "properties": {
                        "id": {"type": "string"},
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "label": {"type": "string", "maxLength": MAX_LABEL_LEN},
                        "kind": {"enum": list(EDGE_KINDS)},
                        "tone": {"enum": list(TONES)},
                        "style": {"enum": list(EDGE_STYLES)},
                        "flow": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "mode": {"enum": list(FLOW_MODES)},
                                "tone": {"enum": list(TONES)},
                                "speed": {"enum": list(FLOW_SPEEDS)},
                            },
                        },
                    },
                },
            },
            "groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string", "pattern": ID_PATTERN},
                        "label": {"type": "string", "maxLength": MAX_LABEL_LEN},
                        "type": {"enum": list(GROUP_TYPES)},
                        "members": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "demoPath": {
                "type": "array",
                "maxItems": MAX_DEMO_PATH_LEN,
                "items": {"type": "string"},
            },
        },
    }
