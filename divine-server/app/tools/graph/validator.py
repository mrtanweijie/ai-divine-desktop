"""GraphIR validation — the backend gate in front of the render pipeline.

Implements the full checklist of ``docs/design/020-x6-multi-scenario-20260908.md``
§3 (items 1–8 plus the scenario-specific rules 2b–2h).

Two behaviours are non-negotiable (004 决策 2):

1. **No silent fallback.** An unknown ``kind`` is rejected — never downgraded to
   ``flow``. A silent downgrade teaches the model that a wrong answer is a
   correct one. The structured error is the feedback channel.
2. **Whitelist only.** Unknown keys are rejected outright, so the LLM cannot
   smuggle arbitrary SVG attributes, colours or coordinates into the renderer.

The validator returns a *normalised* copy of the IR on success (stable edge ids,
group ``kind``/``wraps`` aliases folded into ``type``/``members``) so downstream
code never has to deal with two spellings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import schema as S

#: Cap on reported issues — the model needs signal, not a wall of text.
MAX_ISSUES = 40

_COLOUR_RE = re.compile(
    r"(?:^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$)"
    r"|(?:^rgba?\s*\()"
    r"|(?:^hsla?\s*\()"
)
_ID_RE = re.compile(S.ID_PATTERN)
_GUARD_RE = re.compile(r"^(?P<event>.*?)\s*\[\s*(?P<guard>[^\]]*?)\s*\]\s*$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass(frozen=True)
class GraphIrIssue:
    """A single validation problem, addressed by JSON path."""

    path: str
    code: str
    message: str
    hint: str = ""

    def render(self) -> str:
        base = f"{self.path}: {self.message}"
        return f"{base}（{self.hint}）" if self.hint else base


@dataclass
class GraphIrValidation:
    """Validation outcome — ``normalized`` is set only when ``ok`` is true."""

    ok: bool
    issues: tuple[GraphIrIssue, ...] = ()
    warnings: tuple[GraphIrIssue, ...] = ()
    normalized: dict[str, Any] | None = None

    @property
    def error_count(self) -> int:
        return len(self.issues)

    def summary(self, kind_hint: bool = True) -> str:
        """Model-facing error report: compact, path-addressed, actionable."""
        lines = [f"GraphIR 校验失败（{self.error_count} 项）："]
        lines.extend(f"- {issue.render()}" for issue in self.issues)
        if self.warnings:
            lines.append("警告（不阻塞）：")
            lines.extend(f"- {w.render()}" for w in self.warnings)
        # 只有 kind 本身出错时才重复枚举，避免每次报错都拖一条长尾巴。
        if kind_hint and any(issue.path.endswith(".kind") for issue in self.issues):
            lines.append("kind 取值：" + " / ".join(S.GRAPH_KINDS))
        lines.append("请修正后重新调用 render_graph。")
        return "\n".join(lines)


class _Collector:
    """Accumulates issues, stops after :data:`MAX_ISSUES` to bound the payload."""

    def __init__(self) -> None:
        self.issues: list[GraphIrIssue] = []
        self.warnings: list[GraphIrIssue] = []
        self.truncated = False

    def error(self, path: str, code: str, message: str, hint: str = "") -> None:
        if len(self.issues) >= MAX_ISSUES:
            self.truncated = True
            return
        self.issues.append(GraphIrIssue(path, code, message, hint))

    def warn(self, path: str, code: str, message: str, hint: str = "") -> None:
        if len(self.warnings) >= MAX_ISSUES:
            return
        self.warnings.append(GraphIrIssue(path, code, message, hint))

    @property
    def failed(self) -> bool:
        return bool(self.issues)


# --------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------
def _enum_hint(values: tuple[str, ...] | list[str], label: str = "允许值") -> str:
    return f"{label}：{'|'.join(str(v) for v in values)}"


def _check_str(
    c: _Collector,
    path: str,
    value: Any,
    *,
    max_len: int,
    required: bool = False,
    allow_empty: bool = False,
) -> str | None:
    if value is None:
        if required:
            c.error(path, "missing", "缺少必填字段")
        return None
    if not isinstance(value, str):
        c.error(path, "type", f"应为字符串，实际是 {type(value).__name__}")
        return None
    if _CONTROL_RE.search(value):
        c.error(path, "control_char", "包含控制字符")
        return None
    if not allow_empty and not value.strip():
        if required:
            c.error(path, "empty", "不能为空字符串")
        return None
    if len(value) > max_len:
        c.error(path, "too_long", f"长度 {len(value)} 超过上限 {max_len}")
        return None
    return value


def _check_enum(
    c: _Collector,
    path: str,
    value: Any,
    allowed: tuple[str, ...],
    *,
    label: str = "允许值",
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in allowed:
        # 色值已由 _scan_forbidden 精确报错，这里不再重复报一次「非法取值」。
        if isinstance(value, str) and _COLOUR_RE.search(value.strip()):
            return None
        c.error(
            path,
            "enum",
            f"非法取值 {value!r}",
            _enum_hint(allowed, label),
        )
        return None
    return value


def _scan_forbidden(c: _Collector, node: Any, path: str) -> None:
    """Reject coordinates / colours / prototype keys anywhere in the payload."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if key in S.DANGEROUS_KEYS:
                c.error(here, "forbidden_key", "禁止的键名（原型污染）")
                continue
            if key.lower().startswith("on"):
                c.error(here, "forbidden_key", "禁止事件处理器键名（on*）")
                continue
            if key in S.FORBIDDEN_KEYS:
                if key in {"x", "y", "w", "h", "width", "height", "pos", "position",
                           "size", "via", "fromSide", "toSide", "coords", "coordinates"}:
                    c.error(
                        here,
                        "coordinates",
                        "禁止坐标/尺寸字段",
                        "布局由前端 @antv/layout 按 Preset 计算，IR 不含几何信息",
                    )
                elif key == "bc":
                    c.error(
                        here,
                        "palette_index",
                        "禁止分支色索引",
                        "分支色由前端按分支出现顺序自动分配",
                    )
                elif key in {"direction", "shape", "layout"}:
                    c.error(
                        here,
                        "visual_hint",
                        "禁止视觉形态字段",
                        "形态由前端 ScenarioPreset 决定",
                    )
                else:
                    c.error(
                        here,
                        "colour",
                        "禁止色值字段",
                        "颜色由前端 graphTones.ts 主题决定",
                    )
                continue
            _scan_forbidden(c, value, here)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _scan_forbidden(c, item, f"{path}[{index}]")
    elif isinstance(node, str) and _COLOUR_RE.search(node.strip()):
        c.error(path, "colour_literal", f"禁止色值字面量 {node!r}")


def _check_keys(
    c: _Collector,
    value: dict[str, Any],
    path: str,
    allowed: tuple[str, ...],
    *,
    aliases: tuple[str, ...] = (),
) -> None:
    for key in value:
        if key in allowed or key in aliases:
            continue
        # 危险键 / 禁用键已由 _scan_forbidden 精确报错，不再重复报「不认识的字段」。
        if key in S.DANGEROUS_KEYS or key in S.FORBIDDEN_KEYS or key.lower().startswith("on"):
            continue
        c.error(
            f"{path}.{key}",
            "unknown_key",
            "不认识的字段",
            _enum_hint(allowed, "本层允许的字段"),
        )


# --------------------------------------------------------------------------
# Scenario-specific constraints
# --------------------------------------------------------------------------
def _validate_role_fields(
    c: _Collector, path: str, node: dict[str, Any], kind: str
) -> None:
    """Rules 2b / 2c — pseudo, active, icon, type, category, org fields."""
    # icon whitelist (never a URL)
    icon = node.get("icon")
    if icon is not None:
        if not isinstance(icon, str) or icon not in S.NODE_ICONS:
            c.error(
                f"{path}.icon",
                "enum",
                f"非法图标 {icon!r}",
                "只允许内联图标名（禁止 URL / 外链）：" + "|".join(S.NODE_ICONS),
            )
        elif icon not in S.TASK_ICONS and kind not in ("dataflow", "dag"):
            c.warn(
                f"{path}.icon",
                "unused_field",
                f"kind={kind} 不使用 icon，已忽略",
            )

    # UML pseudo states
    pseudo = node.get("pseudo")
    if pseudo is not None:
        if _check_enum(
            c, f"{path}.pseudo", pseudo, S.PSEUDO_STATES, label="伪状态取值"
        ) and kind != "state":
            c.warn(
                f"{path}.pseudo",
                "unused_field",
                f"伪状态仅在 kind=state 生效，kind={kind} 已忽略",
            )

    # execution state (dag / dataflow)
    state = node.get("state")
    if state is not None:
        if _check_enum(
            c,
            f"{path}.state",
            state,
            S.NODE_STATES,
            label="状态取值（映射到 tone，不引入第二套语义色）",
        ) and kind not in ("dag", "dataflow"):
            c.warn(
                f"{path}.state",
                "unused_field",
                f"执行状态仅在 dag/dataflow 生效，kind={kind} 已忽略",
            )

    active = node.get("active")
    if active is not None and not isinstance(active, bool):
        c.error(f"{path}.active", "type", "应为布尔值")

    # concept / arch `type`
    node_type = node.get("type")
    if node_type is not None:
        if not isinstance(node_type, str):
            c.error(f"{path}.type", "type", "应为字符串")
        elif node_type not in S.CONCEPT_TYPES + S.ARCH_TYPES:
            c.error(
                f"{path}.type",
                "enum",
                f"非法类型 {node_type!r}",
                "concept 用 " + "|".join(S.CONCEPT_TYPES)
                + "；arch 用 " + "|".join(S.ARCH_TYPES),
            )
        elif kind == "concept" and node_type not in S.CONCEPT_TYPES:
            c.error(
                f"{path}.type",
                "enum",
                f"{node_type!r} 不是 concept 类型",
                _enum_hint(S.CONCEPT_TYPES),
            )
        elif kind == "arch" and node_type not in S.ARCH_TYPES:
            c.error(
                f"{path}.type",
                "enum",
                f"{node_type!r} 不是 arch 角色",
                _enum_hint(S.ARCH_TYPES),
            )

    # org extras
    count = node.get("count")
    if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 0):
        c.error(f"{path}.count", "type", "应为非负整数")


def _validate_label(
    c: _Collector, path: str, node: dict[str, Any], kind: str
) -> None:
    label = node.get("label")
    has_pseudo = node.get("pseudo") is not None
    if label is None:
        if not has_pseudo:
            c.error(
                f"{path}.label",
                "missing",
                "缺少节点名称",
                "伪状态（pseudo）节点可省略 label，其余节点必填",
            )
        return
    _check_str(c, f"{path}.label", label, max_len=S.MAX_LABEL_LEN, required=True)


def _validate_edge_label(c: _Collector, path: str, label: str) -> None:
    """Rule 2e — UML ``事件[守卫]`` syntax gets the guard hardened."""
    if _CONTROL_RE.search(label):
        c.error(path, "control_char", "标签包含控制字符")
        return
    match = _GUARD_RE.match(label)
    if not match:
        return
    guard = match.group("guard")
    if guard and len(guard) > S.MAX_GUARD_LEN:
        c.error(
            path,
            "guard_too_long",
            f"守卫条件长度 {len(guard)} 超过上限 {S.MAX_GUARD_LEN}",
            "写法：事件[守卫条件]，守卫尽量短（如 超时 [未支付]）",
        )


def _detect_cycle(nodes: list[str], edges: list[tuple[str, str]]) -> list[str] | None:
    """Return one offending cycle (as a path) or ``None`` — used for sequence."""
    adjacency: dict[str, list[str]] = {n: [] for n in nodes}
    for source, target in edges:
        adjacency.setdefault(source, []).append(target)

    state: dict[str, int] = {}
    stack: list[str] = []

    def walk(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for nxt in adjacency.get(node, []):
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if state.get(nxt, 0) == 0:
                found = walk(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in nodes:
        if state.get(node, 0) == 0:
            found = walk(node)
            if found:
                return found
    return None


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def validate_graph_ir(raw: Any) -> GraphIrValidation:
    """Validate a candidate GraphIR and return a normalised copy when valid."""
    c = _Collector()

    if not isinstance(raw, dict):
        c.error("$", "type", f"GraphIR 应为对象，实际是 {type(raw).__name__}")
        return GraphIrValidation(ok=False, issues=tuple(c.issues))

    # ---- deep scan first: coordinates / colours / pollution keys -------------
    _scan_forbidden(c, raw, "$")

    # ---- top level -----------------------------------------------------------
    _check_keys(c, raw, "$", S.TOP_KEYS)

    kind = raw.get("kind")
    if kind is None:
        c.error("$.kind", "missing", "缺少 kind", _enum_hint(S.GRAPH_KINDS, "场景取值"))
    elif not isinstance(kind, str) or kind not in S.GRAPH_KINDS:
        c.error(
            "$.kind",
            "enum",
            f"未知场景 {kind!r}",
            _enum_hint(S.GRAPH_KINDS, "必须是以下之一")
            + "；请按语义选最贴近的场景，不要退化为 flow",
        )
    kind_name = kind if isinstance(kind, str) and kind in S.GRAPH_KINDS else ""

    meta = raw.get("meta")
    if meta is not None:
        if not isinstance(meta, dict):
            c.error("$.meta", "type", "应为对象")
        else:
            _check_keys(c, meta, "$.meta", S.META_KEYS)
            _check_str(c, "$.meta.title", meta.get("title"), max_len=S.MAX_TITLE_LEN)
            _check_str(c, "$.meta.summary", meta.get("summary"), max_len=S.MAX_SUMMARY_LEN)

    # ---- nodes ---------------------------------------------------------------
    raw_nodes = raw.get("nodes")
    node_ids: list[str] = []
    seen_ids: set[str] = set()
    active_count = 0
    categories: list[str] = []
    node_lanes: dict[str, str] = {}
    node_parents: dict[str, str] = {}

    if not isinstance(raw_nodes, list) or not raw_nodes:
        c.error("$.nodes", "missing", "nodes 必须是非空数组")
        raw_nodes = []
    elif kind_name and len(raw_nodes) > S.node_limit(kind_name):
        c.error(
            "$.nodes",
            "limit",
            f"节点数 {len(raw_nodes)} 超过 {kind_name} 上限 {S.node_limit(kind_name)}",
            "拆分多张图，或合并同类节点",
        )

    for index, node in enumerate(raw_nodes):
        path = f"$.nodes[{index}]"
        if not isinstance(node, dict):
            c.error(path, "type", "节点应为对象")
            continue
        _check_keys(c, node, path, S.NODE_KEYS)

        node_id = node.get("id")
        if node_id is None:
            c.error(f"{path}.id", "missing", "缺少节点 id")
        elif not isinstance(node_id, str) or not _ID_RE.match(node_id):
            c.error(
                f"{path}.id",
                "format",
                f"非法节点 id {node_id!r}",
                "只允许字母/数字/下划线/短横线/点/冒号，长度 1–64",
            )
        elif node_id in seen_ids:
            c.error(f"{path}.id", "duplicate", f"节点 id 重复：{node_id}")
        else:
            seen_ids.add(node_id)
            node_ids.append(node_id)

        _validate_label(c, path, node, kind_name)
        _check_enum(c, f"{path}.role", node.get("role"), S.NODE_ROLES, label="语义角色")
        _check_enum(c, f"{path}.tone", node.get("tone"), S.TONES, label="tone 取值")
        _check_str(c, f"{path}.note", node.get("note"), max_len=S.MAX_NOTE_LEN)
        _check_str(c, f"{path}.badge", node.get("badge"), max_len=S.MAX_BADGE_LEN)
        _check_str(c, f"{path}.role_desc", node.get("role_desc"), max_len=S.MAX_ROLE_DESC_LEN)
        _check_str(c, f"{path}.sublabel", node.get("sublabel"), max_len=S.MAX_SUBLABEL_LEN)
        _check_str(c, f"{path}.tag", node.get("tag"), max_len=S.MAX_TAG_LEN)
        _validate_role_fields(c, path, node, kind_name)

        if node.get("active") is True:
            active_count += 1
            if active_count > 1:
                c.error(
                    f"{path}.active",
                    "unique",
                    "active=true 的节点超过 1 个",
                    "全图只能有一个当前激活状态",
                )

        category = node.get("category")
        if category is not None:
            cleaned = _check_str(c, f"{path}.category", category, max_len=S.MAX_CATEGORY_LEN)
            if cleaned and cleaned not in categories:
                categories.append(cleaned)

        lane = node.get("lane")
        if isinstance(lane, str) and lane:
            node_lanes[node_id or path] = lane
        parent = node.get("parent")
        if isinstance(parent, str) and parent:
            node_parents[node_id or path] = parent

    if len(categories) > S.MAX_CATEGORIES:
        c.warn(
            "$.nodes",
            "category_overflow",
            f"类别数 {len(categories)} 超过 {S.MAX_CATEGORIES}，第 "
            f"{S.MAX_CATEGORIES + 1} 类起不着色",
            "把类别归并到 5 个以内",
        )

    # ---- groups --------------------------------------------------------------
    raw_groups = raw.get("groups")
    group_ids: set[str] = set()
    lane_group_ids: set[str] = set()
    boundary_membership: dict[str, int] = {}
    group_members: dict[str, list[str]] = {}

    if raw_groups is not None:
        if not isinstance(raw_groups, list):
            c.error("$.groups", "type", "groups 应为数组")
            raw_groups = []
    else:
        raw_groups = []

    for index, group in enumerate(raw_groups):
        path = f"$.groups[{index}]"
        if not isinstance(group, dict):
            c.error(path, "type", "分组应为对象")
            continue
        _check_keys(c, group, path, S.GROUP_KEYS)

        group_id = group.get("id")
        if group_id is None:
            c.error(f"{path}.id", "missing", "缺少分组 id")
        elif not isinstance(group_id, str) or not _ID_RE.match(group_id):
            c.error(f"{path}.id", "format", f"非法分组 id {group_id!r}")
        elif group_id in group_ids:
            c.error(f"{path}.id", "duplicate", f"分组 id 重复：{group_id}")
        else:
            group_ids.add(group_id)

        # `kind` is the arch-doc spelling of `type`; both accepted, folded later.
        group_type = group.get("type", group.get("kind"))
        resolved_type = _check_enum(
            c, f"{path}.type", group_type, S.GROUP_TYPES, label="容器类型"
        )
        if resolved_type == "lane" and isinstance(group_id, str):
            lane_group_ids.add(group_id)
        _check_str(c, f"{path}.label", group.get("label"), max_len=S.MAX_LABEL_LEN)

        members = group.get("members", group.get("wraps"))
        if members is None:
            c.error(f"{path}.members", "missing", "缺少 members")
            continue
        if not isinstance(members, list) or not members:
            c.error(f"{path}.members", "type", "members 应为非空数组")
            continue
        valid_members: list[str] = []
        for member_index, member in enumerate(members):
            member_path = f"{path}.members[{member_index}]"
            if not isinstance(member, str):
                c.error(member_path, "type", "成员应为节点 id 字符串")
                continue
            if member not in seen_ids:
                c.error(
                    member_path,
                    "reference",
                    f"成员 {member!r} 不是已声明的节点 id",
                    "members 只能引用同一 IR 中已声明的节点",
                )
                continue
            valid_members.append(member)
            if resolved_type in S.BOUNDARY_TYPES:
                boundary_membership[member] = boundary_membership.get(member, 0) + 1
        if isinstance(group_id, str):
            group_members[group_id] = valid_members

    for member, depth in boundary_membership.items():
        if depth > S.MAX_BOUNDARY_DEPTH:
            c.error(
                "$.groups",
                "boundary_depth",
                f"节点 {member!r} 被 {depth} 层边界包裹",
                f"上限 {S.MAX_BOUNDARY_DEPTH} 层：region 内套 security-group 即到顶",
            )

    # ---- edges ---------------------------------------------------------------
    raw_edges = raw.get("edges")
    edge_ids: set[str] = set()
    edge_pairs: list[tuple[str, str]] = []

    if raw_edges is not None:
        if not isinstance(raw_edges, list):
            c.error("$.edges", "type", "edges 应为数组")
            raw_edges = []
    else:
        raw_edges = []

    if kind_name and len(raw_edges) > S.edge_limit(kind_name):
        c.error(
            "$.edges",
            "limit",
            f"边数 {len(raw_edges)} 超过 {kind_name} 上限 {S.edge_limit(kind_name)}",
            "拆分多张图，或合并同类连线",
        )

    for index, edge in enumerate(raw_edges):
        path = f"$.edges[{index}]"
        if not isinstance(edge, dict):
            c.error(path, "type", "边应为对象")
            continue
        _check_keys(c, edge, path, S.EDGE_KEYS)

        edge_id = edge.get("id")
        if edge_id is not None:
            if not isinstance(edge_id, str) or not _ID_RE.match(edge_id):
                c.error(f"{path}.id", "format", f"非法边 id {edge_id!r}")
            elif edge_id in edge_ids:
                c.error(f"{path}.id", "duplicate", f"边 id 重复：{edge_id}")
            else:
                edge_ids.add(edge_id)

        endpoints: list[str] = []
        for field_name in ("source", "target"):
            value = edge.get(field_name)
            value_path = f"{path}.{field_name}"
            if value is None:
                c.error(value_path, "missing", f"缺少 {field_name}")
                endpoints.append("")
                continue
            if not isinstance(value, str) or value not in seen_ids:
                c.error(
                    value_path,
                    "reference",
                    f"{value!r} 不是已声明的节点 id",
                    "source/target 必须引用同一 IR 内的节点",
                )
                endpoints.append("")
                continue
            endpoints.append(value)
        if endpoints[0] and endpoints[1]:
            edge_pairs.append((endpoints[0], endpoints[1]))

        label = _check_str(c, f"{path}.label", edge.get("label"), max_len=S.MAX_LABEL_LEN)
        if label:
            _validate_edge_label(c, f"{path}.label", label)

        _check_enum(c, f"{path}.kind", edge.get("kind"), S.EDGE_KINDS, label="边语义")
        _check_enum(c, f"{path}.tone", edge.get("tone"), S.TONES, label="tone 取值")
        _check_enum(c, f"{path}.style", edge.get("style"), S.EDGE_STYLES, label="线型")

        flow = edge.get("flow")
        if flow is not None:
            if not isinstance(flow, dict):
                c.error(f"{path}.flow", "type", "flow 应为对象")
            else:
                _check_keys(c, flow, f"{path}.flow", ("mode", "tone", "speed"))
                _check_enum(
                    c, f"{path}.flow.mode", flow.get("mode"), S.FLOW_MODES, label="流动模式"
                )
                _check_enum(
                    c, f"{path}.flow.tone", flow.get("tone"), S.TONES, label="tone 取值"
                )
                speed = flow.get("speed")
                if speed is not None and speed not in S.FLOW_SPEEDS:
                    c.error(
                        f"{path}.flow.speed",
                        "enum",
                        f"非法速度 {speed!r}",
                        "允许 0.5 | 1 | 2",
                    )

    # ---- cross-cutting: lane / parent / demoPath / sequence ------------------
    if kind_name == "swimlane":
        if not lane_group_ids:
            c.error(
                "$.groups",
                "missing",
                "kind=swimlane 需要声明泳道",
                "在 groups 中给出 { id, label, type: 'lane', members: [...] }",
            )
        for node_id, lane in node_lanes.items():
            if lane not in lane_group_ids:
                c.error(
                    "$.nodes",
                    "reference",
                    f"节点 {node_id!r} 的 lane={lane!r} 不是已声明的泳道 id",
                    "lane 必须指向 type='lane' 的分组",
                )
        for node in raw_nodes:
            if isinstance(node, dict) and not node.get("lane") and not node.get("pseudo"):
                c.error(
                    "$.nodes",
                    "missing",
                    f"节点 {node.get('id')!r} 缺少 lane",
                    "kind=swimlane 时每个节点必须归属一条泳道",
                )

    for node_id, parent in node_parents.items():
        if parent not in seen_ids and parent not in group_ids:
            c.error(
                "$.nodes",
                "reference",
                f"节点 {node_id!r} 的 parent={parent!r} 不是已声明的节点或分组 id",
            )

    if kind_name == "sequence":
        cycle = _detect_cycle(node_ids, edge_pairs)
        if cycle:
            c.error(
                "$.edges",
                "cycle",
                "时序消息出现环：" + " → ".join(cycle),
                "时序语义本身无环，边数组顺序即时间顺序",
            )

    demo_path = raw.get("demoPath")
    if demo_path is not None:
        if not isinstance(demo_path, list):
            c.error("$.demoPath", "type", "demoPath 应为节点 id 数组")
        else:
            if len(demo_path) > S.MAX_DEMO_PATH_LEN:
                c.error(
                    "$.demoPath",
                    "too_long",
                    f"演示路径长度 {len(demo_path)} 超过上限 {S.MAX_DEMO_PATH_LEN}",
                )
            for index, step in enumerate(demo_path):
                if not isinstance(step, str) or step not in seen_ids:
                    c.error(
                        f"$.demoPath[{index}]",
                        "reference",
                        f"{step!r} 不是已声明的节点 id",
                    )

    if c.failed:
        return GraphIrValidation(
            ok=False, issues=tuple(c.issues), warnings=tuple(c.warnings)
        )

    return GraphIrValidation(
        ok=True,
        warnings=tuple(c.warnings),
        normalized=_normalize(raw, kind_name),
    )


# --------------------------------------------------------------------------
# Normalisation — fold aliases, stabilise edge ids
# --------------------------------------------------------------------------
def _normalize(raw: dict[str, Any], kind: str) -> dict[str, Any]:
    """Return a cleaned copy: only whitelisted keys survive, aliases folded."""
    out: dict[str, Any] = {"kind": kind}

    meta = raw.get("meta")
    if isinstance(meta, dict):
        cleaned_meta = {k: meta[k] for k in S.META_KEYS if isinstance(meta.get(k), str)}
        if cleaned_meta:
            out["meta"] = cleaned_meta

    nodes: list[dict[str, Any]] = []
    for node in raw.get("nodes") or []:
        item = {k: node[k] for k in S.NODE_KEYS if k in node}
        nodes.append(item)
    out["nodes"] = nodes

    edges: list[dict[str, Any]] = []
    for index, edge in enumerate(raw.get("edges") or []):
        item = {k: edge[k] for k in S.EDGE_KEYS if k in edge}
        item.setdefault("id", f"e{index + 1}")
        edges.append(item)
    if edges:
        out["edges"] = edges

    groups: list[dict[str, Any]] = []
    for group in raw.get("groups") or []:
        item: dict[str, Any] = {"id": group["id"]}
        if isinstance(group.get("label"), str):
            item["label"] = group["label"]
        item["type"] = group.get("type", group.get("kind"))
        members = group.get("members", group.get("wraps")) or []
        item["members"] = list(members)
        groups.append(item)
    if groups:
        out["groups"] = groups

    if isinstance(raw.get("demoPath"), list):
        out["demoPath"] = list(raw["demoPath"])

    return out


__all__ = [
    "GraphIrIssue",
    "GraphIrValidation",
    "validate_graph_ir",
]
