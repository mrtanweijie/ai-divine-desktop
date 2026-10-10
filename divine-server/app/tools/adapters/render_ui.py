"""render_ui — 声明式交互面板（A2UI 接入的出站点）。

设计文档：``docs/design/028-a2ui-integration-20261009.md``。

**模型不产出 A2UI JSON**（044 §10.0）。这个工具像 ``render_graph`` 一样，
只收「中立界面 IR」——``{surfaceId, components, data, actions}``——然后：

1. ``validator.validate_ui_surface`` 硬校验（未知组件/属性/引用/环/超限）；
2. ``versions.v0_9_1.to_messages`` 把 IR 翻成 A2UI v0.9.1 消息；
3. 消息随 ``ToolResult.data`` 回到 ``agent/tools/execution.py``，
   由那里用 ``runtime.stream_writer`` 发 ``event: a2ui``。

第 3 步为什么不在这里做：适配器拿不到 ``runtime.stream_writer``
（只有 ``execution.py:217`` 有）。这与 ``scheduled_tasks_changed`` 的
做法一致——事件由执行层按工具名/返回值发射，适配器保持纯函数。

两条设计取舍（都在 044 里论证过）：

* **不做流式**：整块 surface 原子渲染。一帧内 A2UI 消息必须完整，
  不做 JSONL 跨帧拼接（§5.1 帧内完整性铁律）；渐进渲染留到 S5。
* **主题收敛**：忽略 A2UI 的 theme/surfaceProperties，只认 ``tone`` 语义色，
  深浅色由前端 theme 决定（§9.4）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool
from ..ui.catalog import (
    BUILTIN_ACTIONS,
    COMPONENT_NAMES,
    MAX_ACTIONS,
    MAX_COMPONENTS,
    MAX_DEPTH,
    MAX_RICH_MEDIA,
    MAX_SURFACE_CHARS,
    MAX_TABLE_ROWS,
    SURFACE_TOP_KEYS,
    component_hint,
)
from ..ui.ir import extract_surface
from ..ui.validator import validate_ui_surface
from ..ui.versions.v0_9_1 import to_messages

#: 顶层允许的参数：IR 字段本身，外加一个 ``surface`` 嵌套别名。
_ALLOWED_ARGS: frozenset[str] = frozenset(SURFACE_TOP_KEYS) | {"surface"}

DESCRIPTION = (
    "把「一组组件的组合」渲染成一块**可交互面板**：可以同时放说明文字、"
    "徽标、数据表、进度、步骤条与输入控件，用户能在面板里改参数、点按钮，"
    "操作会带着当前面板状态回到对话，形成「看 → 调 → 再看」的闭环。\n"
    "【何时调用】**默认不要调用**。单纯展示结论用正文 Markdown（轻、快、省 token）；"
    "只有当一个回答同时满足下面两条时才调用本工具："
    "① 需要**组合**呈现（至少 3 类内容组织在一起，例如「结论 + 数据表 + 操作按钮」），"
    "② 或用户**需要在界面里改动/操作**（调参数、勾选、点按钮触发下一步）。"
    "只要展示一张图用 generate_chart，只要一张表用 Markdown 表格，"
    "只要一段可点的选项用 options 卡片——都不要用本工具。\n"
    "【硬约束】① 组件必须从下方目录里选，写目录外的名字会被拒绝；"
    "② 必须有且仅有一个 id 为 `root` 的根组件，其余组件从它可达；"
    "③ 只描述「展示什么 + 能做什么」：**禁止坐标、色值、样式、HTML、脚本**，"
    "颜色只能用 tone 语义色；"
    f"④ 组件总数 ≤ {MAX_COMPONENTS}，嵌套深度 ≤ {MAX_DEPTH}，"
    f"动作数 ≤ {MAX_ACTIONS}，Table 行数 ≤ {MAX_TABLE_ROWS}（超了请导出成文件）；"
    "⑤ 业务动作（非内置）必须在 actions 里登记，不允许临时发明。\n"
    f"【内置动作】{' | '.join(BUILTIN_ACTIONS)}（无需登记）。\n"
    f"【组件目录】{component_hint()}。\n"
    "【属性速查】"
    "布局：Column/Row{children:[id], gap, align}、Card{child, title}、Divider；"
    "展示：Text{text, variant:h1..h4|body|caption, tone}、Badge{text, tone}、"
    "Image{url, aspectRatio, alt}、"
    "Table{columns:[{key,title}], rows:[{列key:值}]（**行对象数组，不是二维数组**）, maxHeight}、"
    "Progress{value:0..1, label}、Steps{items:[{label,status}]}；"
    "输入：TextField/TextArea{label, value}、NumberField{label, value, min, max, unit}、"
    "Select{label, value, options:[{value,label}]}、"
    "ChoicePicker{value, options, multiple}、Checkbox/Switch{label, checked}；"
    "动作：Button{text, variant:primary|ghost|danger, action}；"
    "富媒体（**同屏合计最多 "
    f"{MAX_RICH_MEDIA} 个，且同类各限 1 个**，会显著拖慢滚动）："
    "Chart{option, height}、Graph{ir, height}、FileList{files:[{name,path?,size?}]}。\n"
    "【数据绑定】组件属性可写 {\"path\": \"/a/b\"} 去引用 data 里的值（RFC 6901），"
    "例如 value:{\"path\":\"/target/labor\"}；**该路径必须已存在于 data**，"
    "否则会被拒绝。输入控件的 value/checked 建议都走绑定，这样面板内改动能回流。\n"
    "【动作】Button.action = {name, context?}；context 是 [{key, value}]，"
    "value 可直接写值或写绑定，用于把面板里改过的值随动作带回后端。"
    "**省略 context 时会自动带上面板内所有输入控件的当前值**（防你漏写导致"
    "用户填的数字丢失）；确实不需要参数的动作请显式写 `context: []`。"
    "面板渲染完**不要在正文里重复面板里的数据**，只需给结论或下一步建议。"
)


def _surface_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "surfaceId": {
                "type": "string",
                "description": (
                    "面板标识（必填），短英文+连字符，如 cost-panel。"
                    "同一个 surfaceId 再次出现表示**原地刷新**旧面板，而不是新开一块。"
                ),
            },
            "title": {"type": "string", "description": "面板标题（可选，≤40 字）"},
            "components": {
                "type": "array",
                "description": (
                    "组件数组（邻接表：扁平列表，用 id 互相引用，必须含 id 为 root 的根）。"
                    "每项 {id, component, ...属性}"
                ),
                "items": {
                    "type": "object",
                    "required": ["id", "component"],
                    "properties": {
                        "id": {"type": "string", "description": "唯一 id，短英文/数字"},
                        "component": {
                            "type": "string",
                            "description": (
                                f"组件名，必须是目录内的 {len(COMPONENT_NAMES)} 个之一"
                            ),
                        },
                    },
                    "additionalProperties": True,
                },
            },
            "data": {
                "type": "object",
                "description": (
                    "面板数据模型（可选）。被 {\"path\":\"/a/b\"} 引用的路径必须在这里存在。"
                    "例如 {\"rows\": [...], \"target\": {\"labor\": 30}}"
                ),
            },
            "actions": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    f"本面板用到的**业务动作**名登记表（可选，≤{MAX_ACTIONS}）。"
                    f"内置动作 {' | '.join(BUILTIN_ACTIONS)} 不必登记"
                ),
            },
        },
        "required": ["surfaceId", "components"],
    }


@register_tool("render_ui", DESCRIPTION, _surface_schema())
class RenderUiAdapter(ToolAdapter):
    """校验中立 IR 并翻译成 A2UI v0.9.1 消息；渲染在前端。"""

    category = "ui"
    timeout = 15

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return arguments or {}

    @staticmethod
    def _reject_unknown_args(arguments: dict[str, Any]) -> None:
        unknown = [key for key in arguments if key not in _ALLOWED_ARGS]
        nested = arguments.get("surface")
        if isinstance(nested, dict):
            unknown += [
                f"surface.{key}" for key in nested if key not in SURFACE_TOP_KEYS
            ]
        if unknown:
            raise ToolExecutionError(
                "render_ui 参数包含不认识的字段："
                + ", ".join(sorted(unknown))
                + "。允许的顶层字段："
                + ", ".join(sorted(_ALLOWED_ARGS))
                + "（组件与属性约束见工具说明）。"
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
        surface = extract_surface(arguments)

        validation = validate_ui_surface(surface)
        if not validation.ok:
            # 结构化硬报错（不静默降级）：模型据此自纠后重试。
            raise ToolExecutionError(validation.summary())

        normalized = validation.normalized or {}
        messages = to_messages(normalized)
        serialized = json.dumps(normalized, ensure_ascii=False)
        if len(serialized) > MAX_SURFACE_CHARS:
            raise ToolExecutionError(
                f"面板体积 {len(serialized)} 字符超过上限 {MAX_SURFACE_CHARS}；"
                "请减少组件数量或缩短文本。"
            )

        surface_id = str(normalized.get("surfaceId") or "")
        component_count = len(normalized.get("components") or [])
        action_names = _collect_action_names(normalized)

        note = (
            f"✓ 已渲染交互面板（surfaceId={surface_id}，"
            f"{component_count} 个组件，{len(action_names)} 个动作"
            + (f"：{' / '.join(action_names)}" if action_names else "")
            + "）。面板已直接呈现给用户，不需要在正文里重复其中数据。"
        )
        if validation.warnings:
            note += "；提示：" + "；".join(w.message for w in validation.warnings)

        return ToolResult(
            success=True,
            message=note,
            # 模型只看规模摘要，不看回完整 JSON（省 token，也避免它复述面板内容）。
            content=json.dumps(
                {
                    "success": True,
                    "message": note,
                    "surfaceId": surface_id,
                    "components": component_count,
                    "actions": action_names,
                },
                ensure_ascii=False,
            ),
            data={
                # 归一化后的中立 IR：持久化与前端兜底都用它（044 §5.3 / §5.4）。
                "uiSurface": normalized,
                # A2UI v0.9.1 消息：由 execution 层发 `event: a2ui`；发完即丢弃，
                # 不随 tool result 再传一遍（避免同内容双份）。
                "a2uiMessages": messages,
                "surfaceId": surface_id,
                "actionNames": action_names,
            },
        )


def _collect_action_names(normalized: dict[str, Any]) -> list[str]:
    """按声明顺序收集面板里真正用到的动作名（去重）。"""
    seen: list[str] = []
    for component in normalized.get("components") or []:
        action = component.get("action")
        if not isinstance(action, dict):
            continue
        name = action.get("name")
        if isinstance(name, str) and name and name not in seen:
            seen.append(name)
    return seen
