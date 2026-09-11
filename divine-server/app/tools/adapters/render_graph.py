"""render_graph — declarative graph rendering for the interactive X6 pipeline.

The Agent supplies *topology and semantics only*; the frontend resolves layout,
node shapes, routing, interaction level and motion through its ScenarioPreset
table. That split is what keeps this tool stable: adding a scenario is one new
row in the frontend preset table, not a schema change here.

Design docs:
- ``docs/design/020-x6-multi-scenario-20260908.md`` §3 (IR + validation), §4 (presets)
- ``docs/plan/004-interactive-flowchart-20260908.md`` 决策 1/2/13/15

Two behaviours matter more than the rest:

* **No silent fallback.** An unknown ``kind`` is a hard error carrying the legal
  enum, so the model can correct itself instead of shipping a flow chart when the
  user asked for a state machine.
* **No streaming.** The tool returns the *complete* validated IR in one go; the
  entrance animation is replayed client-side. See 004 决策 13.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..graph import schema as S
from ..graph.validator import GraphIrValidation, validate_graph_ir
from ..registry import register_tool

#: Hard ceiling on the serialised IR. Validation already bounds nodes, edges and
#: every string, so this only catches pathological payloads.
MAX_IR_CHARS = 200_000

#: Arguments accepted at the top level (the IR itself, plus a ``graph`` alias).
_ALLOWED_ARGS: frozenset[str] = frozenset(S.TOP_KEYS) | {"title", "graph"}

#: The nested ``graph`` alias accepts the IR plus a convenience ``title``.
_ALLOWED_GRAPH_KEYS: frozenset[str] = frozenset(S.TOP_KEYS) | {"title"}

_KIND_LINES = "；".join(
    f"{kind} {S.KIND_LABELS[kind]}" for kind in S.GRAPH_KINDS
)

DESCRIPTION = (
    "把「节点 + 边」类图渲染为**可交互图形**：可点击查看详情、可播放数据流动画、"
    "可演示路径、可导出 PNG/SVG。\n"
    "【何时调用】**默认不要调用本工具**。一切图形需求先用 mermaid 代码块输出静态图"
    "（轻、快、省 token）；只有当用户在静态图基础上要求**交互 / 动画 / 数据流动 / 演示播放 / "
    "导出图片**，或明确要求「可交互的图」「可编辑的图」时，才调用本工具，把**已经确认的拓扑**"
    "转成 GraphIR 重绘——用户无需重新描述一遍。统计图表用 generate_chart；"
    "地图 / 平面图 / 电路图不支持，直接说明。\n"
    "【硬约束】① 只描述「画什么」：**禁止任何坐标（x/y/w/h/pos/size）、色值、布局或形状字段**"
    "——布局与配色由前端预设决定，写了会被拒绝；② kind 必须是下列 15 个场景之一，"
    "写错会被拒绝，不要退化成 flow；③ 节点 id 用简短英文/数字，label 是给用户看的中文短名"
    "（≤60 字）；④ 边用 source/target 引用节点 id；⑤ 需要体现数据流向的边加 "
    "flow:{mode:'antline'}，异常/成功等状态用 tone 标记（不要写颜色）；"
    "⑥ 节点数不要超过场景上限，超了会被拒绝并提示。\n"
    f"【场景 kind】{_KIND_LINES}。\n"
    "【字段速查】节点：{id, label, role?, tone?, note?, badge?}；"
    "边的语义 kind ∈ " + "|".join(S.EDGE_KINDS) + "，线型 style ∈ " + "|".join(S.EDGE_STYLES) + "；"
    "role ∈ " + "|".join(S.NODE_ROLES) + "；"
    "tone ∈ " + "|".join(S.TONES) + "（neutral 与 info 视觉等同，只有 success/warning/error 上色）。\n"
    "【场景特有可选字段】dag/dataflow：state ∈ " + "|".join(S.NODE_STATES)
    + "、icon ∈ 内联图标名（" + "|".join(S.NODE_ICONS) + "，禁止 URL）；"
    "state：pseudo ∈ " + "|".join(S.PSEUDO_STATES) + "、active（全图最多 1 个）；"
    "org：role_desc（职位/编制）、count（直属人数，画折叠角标）；"
    "concept：type ∈ " + "|".join(S.CONCEPT_TYPES) + "；"
    "arch：type ∈ " + "|".join(S.ARCH_TYPES) + "、sublabel（技术栈/端口）、tag（徽标）；"
    "swimlane：lane（必须在 groups 里声明同名泳道）；"
    "mindmap/org：parent（父节点 id）。\n"
    "【分组 groups】{id, label, type ∈ " + "|".join(S.GROUP_TYPES) + ", members:[节点 id]}；"
    "分层架构用 region/vpc/security-group（最多两层包裹，渲染为重叠框）；"
    "泳道用 type:'lane'；普通虚线分组用 type:'cluster'。"
)


@register_tool(
    "render_graph",
    DESCRIPTION,
    {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": list(S.GRAPH_KINDS),
                "description": (
                    "场景类型（必填）。按语义选最贴近的一个："
                    + "；".join(f"{k}={S.KIND_LABELS[k]}" for k in S.GRAPH_KINDS)
                ),
            },
            "title": {
                "type": "string",
                "description": "图标题，建议写结论（≤60 字），如「订单支付链路」",
            },
            "nodes": {
                "type": "array",
                "description": (
                    "节点列表。每项 {id, label, role?, tone?, note?, badge?} 加场景特有可选字段；"
                    "禁止坐标/色值字段"
                ),
                "items": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string", "description": "唯一 id，短英文/数字"},
                        "label": {"type": "string", "description": "展示名（中文短名，≤60 字）"},
                        "role": {
                            "type": "string",
                            "enum": list(S.NODE_ROLES),
                            "description": "语义角色，决定节点形态",
                        },
                        "tone": {
                            "type": "string",
                            "enum": list(S.TONES),
                            "description": "语义色（仅 success/warning/error 上色）",
                        },
                        "note": {"type": "string", "description": "点击节点时的详情文本"},
                        "badge": {"type": "string", "description": "角标短文本，如 P0 / 30m"},
                        "state": {"type": "string", "enum": list(S.NODE_STATES)},
                        "icon": {"type": "string", "enum": list(S.NODE_ICONS)},
                        "pseudo": {"type": "string", "enum": list(S.PSEUDO_STATES)},
                        "active": {"type": "boolean", "description": "当前激活状态，全图最多 1 个"},
                        "role_desc": {"type": "string", "description": "org：职位/编制"},
                        "count": {"type": "integer", "description": "org：直属子节点数"},
                        "type": {
                            "type": "string",
                            "enum": list(S.CONCEPT_TYPES + S.ARCH_TYPES),
                        },
                        "category": {
                            "type": "string",
                            "description": "类别名（arch/工作流场景，最多 5 类，不要写颜色）",
                        },
                        "sublabel": {"type": "string", "description": "arch：技术栈/端口"},
                        "tag": {"type": "string", "description": "arch：右上角徽标"},
                        "lane": {"type": "string", "description": "swimlane：所属泳道 id"},
                        "parent": {"type": "string", "description": "层次归属（org/mindmap）"},
                    },
                },
            },
            "edges": {
                "type": "array",
                "description": "边列表；source/target 必须引用已声明的节点 id",
                "items": {
                    "type": "object",
                    "required": ["source", "target"],
                    "properties": {
                        "id": {"type": "string"},
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "label": {
                            "type": "string",
                            "description": "边标签；state 场景支持 UML 写法 事件[守卫]",
                        },
                        "kind": {"type": "string", "enum": list(S.EDGE_KINDS)},
                        "tone": {"type": "string", "enum": list(S.TONES)},
                        "style": {"type": "string", "enum": list(S.EDGE_STYLES)},
                        "flow": {
                            "type": "object",
                            "description": "数据流动画（可选）",
                            "properties": {
                                "mode": {"type": "string", "enum": list(S.FLOW_MODES)},
                                "tone": {"type": "string", "enum": list(S.TONES)},
                                "speed": {
                                    "type": "number",
                                    "enum": list(S.FLOW_SPEEDS),
                                    "description": "0.5 慢 / 1 常规 / 2 快",
                                },
                            },
                        },
                    },
                },
            },
            "groups": {
                "type": "array",
                "description": "分组/泳道/边界；泳道用 type:'lane'，分层用 region/security-group",
                "items": {
                    "type": "object",
                    "required": ["id", "type", "members"],
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "type": {"type": "string", "enum": list(S.GROUP_TYPES)},
                        "members": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "成员节点 id 列表",
                        },
                    },
                },
            },
            "demoPath": {
                "type": "array",
                "items": {"type": "string"},
                "description": "演示路径（节点 id 顺序，可选）；提供后工具条出现「播放演示」",
            },
        },
        "required": ["kind", "nodes"],
    },
)
class RenderGraphAdapter(ToolAdapter):
    """Validate and pass through a GraphIR; rendering happens on the frontend."""

    category = "diagrams"
    timeout = 15

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return arguments or {}

    @staticmethod
    def _extract_ir(arguments: dict[str, Any]) -> dict[str, Any]:
        """Fold flat arguments (or a ``graph`` alias) into a single IR object.

        Only whitelisted IR keys are lifted out of the nested form — its
        ``title`` is folded into ``meta`` rather than leaking into the IR, where
        it would be rejected as an unknown field.
        """
        source: dict[str, Any] = {}
        nested = arguments.get("graph")
        if isinstance(nested, dict):
            for key in S.TOP_KEYS:
                if key in nested:
                    source[key] = nested[key]
            source = RenderGraphAdapter._merge_title(source, nested.get("title"))
        for key in S.TOP_KEYS:
            if key in arguments:
                source[key] = arguments[key]
        # 顶层 title 是 schema 声明的正式参数，优先于嵌套 graph 里的同名值。
        return RenderGraphAdapter._merge_title(
            source, arguments.get("title"), override=True
        )

    @staticmethod
    def _merge_title(
        source: dict[str, Any], title: Any, *, override: bool = False
    ) -> dict[str, Any]:
        if not isinstance(title, str) or not title.strip():
            return source
        meta = source.get("meta")
        meta = dict(meta) if isinstance(meta, dict) else {}
        if override or not meta.get("title"):
            meta["title"] = title.strip()
        source["meta"] = meta
        return source

    @staticmethod
    def _reject_unknown_args(arguments: dict[str, Any]) -> None:
        unknown = [key for key in arguments if key not in _ALLOWED_ARGS]
        nested = arguments.get("graph")
        if isinstance(nested, dict):
            unknown += [
                f"graph.{key}" for key in nested if key not in _ALLOWED_GRAPH_KEYS
            ]
        if unknown:
            raise ToolExecutionError(
                "render_graph 参数包含不认识的字段："
                + ", ".join(sorted(unknown))
                + "。允许的顶层字段："
                + ", ".join(sorted(_ALLOWED_ARGS))
                + "（节点/边的字段约束见工具说明）。"
            )

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any | None = None,
    ) -> ToolResult:
        del workspace, locale, progress_callback  # 纯校验，无 IO
        arguments = arguments or {}

        self._reject_unknown_args(arguments)
        ir = self._extract_ir(arguments)

        validation: GraphIrValidation = validate_graph_ir(ir)
        if not validation.ok:
            # 结构化报错（不是静默降级）：模型据此自纠后重新调用。
            raise ToolExecutionError(validation.summary())

        normalized = validation.normalized or {}
        serialized = json.dumps(normalized, ensure_ascii=False)
        if len(serialized) > MAX_IR_CHARS:
            raise ToolExecutionError(
                f"GraphIR 体积 {len(serialized)} 字符超过上限 {MAX_IR_CHARS}；"
                "请减少节点/边的数量或缩短标签。"
            )

        kind = normalized.get("kind", "")
        node_count = len(normalized.get("nodes") or [])
        edge_count = len(normalized.get("edges") or [])
        title = (normalized.get("meta") or {}).get("title") or S.KIND_LABELS.get(kind, kind)

        note = f"✓ {title}（{S.KIND_LABELS.get(kind, kind)}，{node_count} 节点 / {edge_count} 条边）"
        if validation.warnings:
            note += "；提示：" + "；".join(w.message for w in validation.warnings)

        return ToolResult(
            success=True,
            message=note,
            # 模型只需知道成功与规模；完整 IR 走 data 给前端渲染与持久化。
            content=json.dumps(
                {
                    "success": True,
                    "message": note,
                    "kind": kind,
                    "nodes": node_count,
                    "edges": edge_count,
                },
                ensure_ascii=False,
            ),
            data={
                "graphIR": normalized,
                "kind": kind,
                "title": title,
                "spec_version": 1,
            },
        )
