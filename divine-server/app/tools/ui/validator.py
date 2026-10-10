"""A2UI 中立 IR 的校验器。

设计文档：``docs/design/028-a2ui-integration-20261009.md`` §9.1（L2 层）。

与 ``app/tools/graph/validator.py`` 同一范式，两点必须一致：

* **不静默降级**。未知组件 / 未知属性 / 引用缺失 / 成环 / 超限一律硬报错；
  报错文本携带**合法枚举 + 出错路径**，模型照抄即可自纠（多模型环境下
  这比「让它重试一次」便宜得多）。
* **不信任工具参数 schema**。``agent/core/schema.py:_make_args_model``
  生成的是 ``extra="allow"`` 的 pydantic 模型，未声明的属性不会被拦，
  所以真正的防线在这里（以及前端的 ``parseUISurface.ts``）。

与 GraphIR 的差异：图只有一层「节点 + 边」，这里的组件是**邻接表 + 树**，
因此多了三件事——唯一 id、可达性、成环与深度。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..graph.validator import validate_graph_ir
from .catalog import (
    ACTION_NAME_PATTERN,
    BINDING_KEY,
    BUILTIN_ACTIONS,
    CATALOG_ID,
    CHART_OPTION_DROPPED_KEYS,
    COMPONENT_NAMES,
    COMPONENT_RESERVED_KEYS,
    COMPONENTS,
    MAX_ACTIONS,
    MAX_CHART,
    MAX_CHART_OPTION_CHARS,
    MAX_COMPONENTS,
    MAX_DEPTH,
    MAX_FILE_ITEMS,
    MAX_GRAPH,
    MAX_RICH_MEDIA,
    MAX_TABLE_ROWS,
    RICH_MEDIA_COMPONENTS,
    STEP_STATUSES,
    SURFACE_TOP_KEYS,
)

#: 报错最多列这么多条，避免一次回灌几千字把上下文吃光。
MAX_REPORTED_ERRORS = 12

#: Graph 组件内嵌 GraphIR 时，最多转述这么多条图校验错误
#: （后面会提示模型"先单独调 render_graph 把 IR 调通"）。
MAX_GRAPH_IR_ERRORS = 6

#: 组件 id 形态：短英文/数字，便于前端 React key 与调试。
_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")

#: 树的根组件 id（A2UI 约定，044 §1.2）。
ROOT_ID = "root"

#: Image.url 允许的 data URI 前缀（只放行图片）。
_DATA_URI_PREFIXES = (
    "data:image/png",
    "data:image/jpeg",
    "data:image/webp",
    "data:image/gif",
)

_TYPE_LABELS: dict[str, str] = {
    "string": "字符串",
    "integer": "整数",
    "number": "数字",
    "boolean": "布尔值",
    "children": "组件 id 列表",
    "child": "组件 id",
    "options": "选项数组 [{value,label}]",
    "columns": "列定义数组 [{key,title}]",
    "steps": "步骤数组 [{label,status}]",
    "action": "动作对象 {name,context?}",
    "array": "数组",
    "chartOption": "ECharts option 对象",
    "graphIR": "GraphIR 对象",
    "fileItems": "文件项数组 [{name,path?,size?}]",
}

_MISSING = object()


@dataclass
class UiIssue:
    """一条校验信息。``path`` 可直接照抄定位（如 ``components[3].child``）。"""

    path: str
    message: str
    hint: str = ""

    def render(self) -> str:
        text = f"{self.path} {self.message}"
        if self.hint:
            text += f"；{self.hint}"
        return text


@dataclass
class UiValidation:
    ok: bool
    normalized: dict[str, Any] | None = None
    errors: list[UiIssue] = field(default_factory=list)
    warnings: list[UiIssue] = field(default_factory=list)

    def summary(self) -> str:
        """给模型看的报错文本：逐条带路径，可照抄修正后重试。"""
        lines = [f"render_ui 校验未通过（{len(self.errors)} 处）："]
        for index, issue in enumerate(self.errors[:MAX_REPORTED_ERRORS], start=1):
            lines.append(f"{index}) {issue.render()}")
        if len(self.errors) > MAX_REPORTED_ERRORS:
            lines.append(
                f"…另有 {len(self.errors) - MAX_REPORTED_ERRORS} 处同类问题未列出，"
                "请一并检查。"
            )
        lines.append(
            "修正后重新调用本工具。组件清单与属性约束见工具说明；"
            "不要为了绕过校验而删掉必要字段。"
        )
        return "\n".join(lines)


def _is_binding(value: Any) -> bool:
    """``{"path": "..."}`` —— 本方案唯一的数据绑定形式。"""
    return (
        isinstance(value, dict)
        and set(value) == {BINDING_KEY}
        and isinstance(value.get(BINDING_KEY), str)
    )


def _scalar_ok(value: Any, type_: str) -> bool:
    if type_ == "string":
        return isinstance(value, str)
    if type_ == "boolean":
        return isinstance(value, bool)
    if type_ == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_ == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


class _SurfaceValidator:
    """一次校验的上下文：错误收集 + 组件表 + 父子关系。"""

    def __init__(self, surface: dict[str, Any], catalog_id: str | None) -> None:
        self.surface = surface
        self.catalog_id = catalog_id
        self.errors: list[UiIssue] = []
        self.warnings: list[UiIssue] = []
        #: id -> 原始组件对象（按声明顺序）
        self.by_id: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []
        #: id -> 子组件 id 列表
        self.children_of: dict[str, list[str]] = {}
        #: (owner_path, 子 id 列表)，用于报引用缺失时定位
        self.ref_paths: list[tuple[str, list[str]]] = []
        self.data: dict[str, Any] = {}
        self.declared_actions: set[str] = set()
        self.reachable: set[str] = set()

    # -- 收集 -----------------------------------------------------------
    def error(self, path: str, message: str, hint: str = "") -> None:
        self.errors.append(UiIssue(path, message, hint))

    def warn(self, path: str, message: str, hint: str = "") -> None:
        self.warnings.append(UiIssue(path, message, hint))

    @staticmethod
    def _enum_hint(values: Any) -> str:
        return "合法值：" + " | ".join(str(v) for v in values)

    # -- 顶层 -----------------------------------------------------------
    def check_top_level(self) -> None:
        unknown = [key for key in self.surface if key not in SURFACE_TOP_KEYS]
        if unknown:
            self.error(
                "<surface>",
                "包含不认识的字段：" + ", ".join(sorted(unknown)),
                "允许的顶层字段：" + ", ".join(SURFACE_TOP_KEYS),
            )
        if self.catalog_id is not None and self.catalog_id != CATALOG_ID:
            self.error(
                "catalogId",
                f"目录 {self.catalog_id!r} 不被支持",
                f"本客户端只支持 {CATALOG_ID}（不要自行编造目录地址）",
            )
        surface_id = self.surface.get("surfaceId")
        if not isinstance(surface_id, str) or not surface_id.strip():
            self.error("surfaceId", "必须是非空字符串", "用于面板原地刷新与动作幂等")
        title = self.surface.get("title")
        if title is not None and not isinstance(title, str):
            self.error("title", "类型应为字符串")
        data = self.surface.get("data")
        if data is None:
            self.data = {}
        elif isinstance(data, dict):
            self.data = data
        else:
            self.error("data", "类型应为对象（键 → 值）")
        self._check_actions_declaration()

    def _check_actions_declaration(self) -> None:
        declared = self.surface.get("actions")
        if declared is None:
            return
        if not isinstance(declared, list):
            self.error("actions", "类型应为字符串数组", '如 ["recalc", "export_pdf"]')
            return
        if len(declared) > MAX_ACTIONS:
            self.error(
                f"actions（{len(declared)} 项）",
                f"超过上限 {MAX_ACTIONS}",
                "动作区不要变成菜单栏；超出请拆分面板",
            )
        for index, name in enumerate(declared):
            if not isinstance(name, str) or not _ID_PATTERN.match(name) or not re.match(
                ACTION_NAME_PATTERN, name
            ):
                self.error(
                    f"actions[{index}]",
                    f"{name!r} 不是合法动作名",
                    "小写字母开头，仅含小写字母/数字/下划线，≤32 字符",
                )
                continue
            if name in BUILTIN_ACTIONS:
                self.warn(f"actions[{index}]", f"{name!r} 是内置动作，无需重复登记")
                continue
            self.declared_actions.add(name)

    # -- 组件 -----------------------------------------------------------
    def check_components(self) -> None:
        components = self.surface.get("components")
        if not isinstance(components, list) or not components:
            self.error("components", "必须是非空数组", "面板至少包含一个 root 组件")
            return
        if len(components) > MAX_COMPONENTS:
            self.error(
                f"components（{len(components)} 个）",
                f"超过上限 {MAX_COMPONENTS}",
                "请拆成多次 render_ui 调用，或改用正文 Markdown 呈现",
            )
        for index, raw in enumerate(components):
            self._check_component(index, raw)
        if not self.by_id:
            return
        self._check_root()
        self._check_references()
        self._check_unreachable()
        self._check_cycles_and_depth()
        self._check_rich_media()

    def _check_component(self, index: int, raw: Any) -> None:
        path = f"components[{index}]"
        if not isinstance(raw, dict):
            self.error(path, "每一项都必须是对象")
            return
        component_id = raw.get("id")
        if not isinstance(component_id, str) or not component_id.strip():
            self.error(f"{path}.id", "缺少 id（必填）", "短英文/数字，全局唯一")
            return
        if not _ID_PATTERN.match(component_id):
            self.error(
                f"{path}.id = {component_id!r}",
                "不符合 id 命名规则",
                "字母开头，仅含字母/数字/下划线/连字符，≤32 字符",
            )
        if component_id in self.by_id:
            self.error(f"{path}.id = {component_id!r}", "与前面的组件 id 重复", "id 必须唯一")
            return
        kind = raw.get("component")
        if not isinstance(kind, str) or kind not in COMPONENTS:
            self.error(
                f"{path}.component = {kind!r}",
                "不是合法组件名",
                self._enum_hint(COMPONENT_NAMES),
            )
            return
        self.by_id[component_id] = raw
        self.order.append(component_id)
        self._check_props(path, component_id, kind, raw)

    def _check_props(
        self, path: str, component_id: str, kind: str, raw: dict[str, Any]
    ) -> None:
        props: dict[str, dict[str, Any]] = COMPONENTS[kind]["props"]
        unknown = [
            key for key in raw if key not in props and key not in COMPONENT_RESERVED_KEYS
        ]
        if unknown:
            self.error(
                f"{path}（{kind}）",
                "包含不认识的属性：" + ", ".join(sorted(unknown)),
                f"{kind} 允许的属性：" + (", ".join(props) or "（无）"),
            )
        for name, prop_spec in props.items():
            if name not in raw:
                if prop_spec.get("required"):
                    self.error(
                        f"{path}.{name}",
                        f"{kind} 缺少必填属性",
                        "应为" + _TYPE_LABELS.get(str(prop_spec["type"]), str(prop_spec["type"])),
                    )
                continue
            self._check_prop_value(
                path, component_id, kind, name, raw[name], prop_spec
            )
        if kind == "Image":
            self._check_image_url(f"{path}.url", raw.get("url"))
        if kind == "Table":
            self._check_table_rows(f"{path}.rows", raw.get("rows"))
        if kind == "Progress":
            value = raw.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if not 0 <= float(value) <= 1:
                    self.error(f"{path}.value", f"{value} 超出 0..1", "进度用小数表示")

    def _check_prop_value(
        self,
        owner_path: str,
        owner_id: str,
        kind: str,
        name: str,
        value: Any,
        prop_spec: dict[str, Any],
    ) -> None:
        path = f"{owner_path}.{name}"
        type_ = str(prop_spec["type"])
        enum = prop_spec.get("enum") or ()

        if _is_binding(value):
            if not prop_spec.get("bindable"):
                self.error(
                    path,
                    f"{kind}.{name} 不支持数据绑定 {{path}}",
                    "应直接写" + _TYPE_LABELS.get(type_, type_) + "字面量",
                )
                return
            self._check_binding_path(path, str(value[BINDING_KEY]))
            return

        if type_ == "children":
            self._check_children(path, owner_id, value)
            return
        if type_ == "child":
            self._check_child(path, owner_id, value)
            return
        if type_ == "options":
            self._check_options(path, value)
            return
        if type_ == "columns":
            self._check_columns(path, value)
            return
        if type_ == "steps":
            self._check_steps(path, value)
            return
        if type_ == "action":
            self._check_action(path, value)
            return
        if type_ == "chartOption":
            self._check_chart_option(path, value)
            return
        if type_ == "graphIR":
            self._check_graph_ir(path, value)
            return
        if type_ == "fileItems":
            self._check_file_items(path, value)
            return

        if isinstance(value, dict):
            self.error(
                path,
                '对象只能写成数据绑定 {"path": "/a/b"}',
                "或改成" + _TYPE_LABELS.get(type_, type_) + "字面量",
            )
            return
        if type_ == "array":
            if not isinstance(value, list):
                self.error(path, "类型应为数组")
            return
        if not _scalar_ok(value, type_):
            self.error(path, f"类型应为{_TYPE_LABELS.get(type_, type_)}（收到 {value!r}）")
            return
        if enum and value not in tuple(enum):
            self.error(f"{path} = {value!r}", "不是允许的取值", self._enum_hint(enum))

    def _check_binding_path(self, path: str, pointer: str) -> None:
        if not pointer.startswith("/"):
            self.error(
                f"{path} 的 path = {pointer!r}",
                "不是合法 JSON Pointer",
                "必须以 / 开头，如 /target/labor",
            )
            return
        if self._resolve_pointer(pointer) is _MISSING:
            top = ", ".join(sorted(self.data)) or "（data 为空）"
            self.error(
                f"{path} 的 path = {pointer!r}",
                "在 data 里找不到对应路径",
                f"data 现有顶层键：{top}",
            )

    def _resolve_pointer(self, pointer: str) -> Any:
        body = pointer.strip("/")
        node: Any = self.data
        if not body:
            return node
        for token in body.split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(node, dict) and token in node:
                node = node[token]
            elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
                node = node[int(token)]
            else:
                return _MISSING
        return node

    def _check_children(self, path: str, owner_id: str, value: Any) -> None:
        if not isinstance(value, list) or not value:
            self.error(path, "children 必须是非空数组", '写子组件 id，如 ["hdr","tbl"]')
            return
        ids: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                self.error(f"{path}[{index}]", "子项必须是组件 id 字符串")
            else:
                ids.append(item)
        self.children_of.setdefault(owner_id, []).extend(ids)
        self.ref_paths.append((path, ids))

    def _check_child(self, path: str, owner_id: str, value: Any) -> None:
        if not isinstance(value, str) or not value:
            self.error(path, "child 必须是单个组件 id 字符串")
            return
        self.children_of.setdefault(owner_id, []).append(value)
        self.ref_paths.append((path, [value]))

    def _check_options(self, path: str, value: Any) -> None:
        if not isinstance(value, list) or not value:
            self.error(path, "options 必须是非空数组", "每项 {value, label}")
            return
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                self.error(item_path, "每一项必须是对象 {value, label}")
                continue
            unknown = [k for k in item if k not in ("value", "label", "desc")]
            if unknown:
                self.error(item_path, "包含不认识的字段：" + ", ".join(sorted(unknown)))
            if "value" not in item:
                self.error(f"{item_path}.value", "缺少 value")
            elif isinstance(item["value"], bool) or not isinstance(
                item["value"], (str, int, float)
            ):
                self.error(f"{item_path}.value", "value 应为字符串或数字")
            if not isinstance(item.get("label"), str):
                self.error(f"{item_path}.label", "缺少 label（给用户看的短名）")

    def _check_columns(self, path: str, value: Any) -> None:
        if not isinstance(value, list) or not value:
            self.error(path, "columns 必须是非空数组", "每项 {key, title}")
            return
        seen: set[str] = set()
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                self.error(item_path, "每一项必须是对象 {key, title}")
                continue
            unknown = [k for k in item if k not in ("key", "title", "width", "align")]
            if unknown:
                self.error(item_path, "包含不认识的字段：" + ", ".join(sorted(unknown)))
            key = item.get("key")
            if not isinstance(key, str) or not key:
                self.error(f"{item_path}.key", "缺少 key（对应行对象字段名）")
            elif key in seen:
                self.error(f"{item_path}.key = {key!r}", "列 key 重复")
            else:
                seen.add(key)
            if not isinstance(item.get("title"), str):
                self.error(f"{item_path}.title", "缺少 title（表头文案）")

    def _check_steps(self, path: str, value: Any) -> None:
        if not isinstance(value, list) or not value:
            self.error(path, "items 必须是非空数组", "每项 {label, status}")
            return
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                self.error(item_path, "每一项必须是对象 {label, status}")
                continue
            if not isinstance(item.get("label"), str) or not item.get("label"):
                self.error(f"{item_path}.label", "缺少 label")
            status = item.get("status")
            if status is not None and status not in STEP_STATUSES:
                self.error(
                    f"{item_path}.status = {status!r}",
                    "不是允许的取值",
                    self._enum_hint(STEP_STATUSES),
                )

    def _check_action(self, path: str, value: Any) -> None:
        if not isinstance(value, dict):
            self.error(path, "必须是动作对象 {name, context?}")
            return
        unknown = [k for k in value if k not in ("name", "context")]
        if unknown:
            self.error(path, "包含不认识的字段：" + ", ".join(sorted(unknown)))
        name = value.get("name")
        if not isinstance(name, str) or not name:
            self.error(f"{path}.name", "缺少动作名")
        elif not re.match(ACTION_NAME_PATTERN, name):
            self.error(
                f"{path}.name = {name!r}",
                "不符合动作命名规则",
                "小写字母开头，仅含小写字母/数字/下划线，≤32 字符",
            )
        elif name not in BUILTIN_ACTIONS and name not in self.declared_actions:
            self.error(
                f"{path}.name = {name!r}",
                "是未登记的业务动作",
                "内置动作：" + " | ".join(BUILTIN_ACTIONS)
                + "；业务动作需在 surface.actions 里声明，不允许临时发明",
            )
        context = value.get("context")
        if context is not None:
            self._check_action_context(f"{path}.context", context)

    def _check_action_context(self, path: str, value: Any) -> None:
        if not isinstance(value, list):
            self.error(
                path,
                "必须是数组",
                '每项 {key, value}，value 可直接写值或 {"path": ...}',
            )
            return
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                self.error(item_path, "每一项必须是对象 {key, value}")
                continue
            unknown = [k for k in item if k not in ("key", "value")]
            if unknown:
                self.error(item_path, "包含不认识的字段：" + ", ".join(sorted(unknown)))
            if not isinstance(item.get("key"), str) or not item.get("key"):
                self.error(f"{item_path}.key", "缺少 key（回传给后端的字段名）")
            if "value" not in item:
                self.error(f"{item_path}.value", "缺少 value")
            elif _is_binding(item["value"]):
                self._check_binding_path(
                    f"{item_path}.value", str(item["value"][BINDING_KEY])
                )

    def _check_image_url(self, path: str, url: Any) -> None:
        if not isinstance(url, str) or not url:
            return  # 必填/类型问题已在通用分支报过
        lowered = url.strip().lower()
        if lowered.startswith(("http://", "https://")):
            return
        if lowered.startswith("data:"):
            if not lowered.startswith(_DATA_URI_PREFIXES):
                self.error(f"{path} = {url!r}", "只接受图片类 data URI")
            return
        if lowered.startswith(("javascript:", "file:", "//")):
            self.error(
                f"{path} = {url!r}",
                "不允许的 URL 形态",
                "仅 http(s) 与工作区相对路径；禁 file:/javascript:",
            )
            return
        if url.startswith("/") or ".." in url.split("/"):
            self.error(
                f"{path} = {url!r}",
                "工作区路径不允许绝对路径或 .. 上跳",
                "请用相对工作区的路径，如 assets/chart.png",
            )

    def _check_table_rows(self, path: str, rows: Any) -> None:
        if _is_binding(rows):
            resolved = self._resolve_pointer(str(rows[BINDING_KEY]))
            if isinstance(resolved, list) and len(resolved) > MAX_TABLE_ROWS:
                self.error(
                    f"{path}（绑定 {rows[BINDING_KEY]}，{len(resolved)} 行）",
                    f"超过上限 {MAX_TABLE_ROWS} 行",
                    "请改用工具导出成文件，再由 FileList 呈现",
                )
            return
        if isinstance(rows, list) and len(rows) > MAX_TABLE_ROWS:
            self.error(
                f"{path}（{len(rows)} 行）",
                f"超过上限 {MAX_TABLE_ROWS} 行",
                "UI 不是数据仓库；请导出成文件",
            )

    # -- 富媒体（S5） ----------------------------------------------------
    def _check_chart_option(self, path: str, value: Any) -> None:
        """Chart.option：只校验**形态与体积**，不校验 ECharts schema。

        抄一份 ECharts 的类型定义进后端，等于给自己埋一个"ECharts 升版就腐化"
        的真源。非法 option 在 ECharts 侧的表现是"图画不出来"（空图），
        不会把页面打崩，所以这里只挡"根本不是对象"和"病态体积"。

        配色在 ``normalized()`` 里被剥掉（044 §9.4），这里不重复处理。
        """
        if not isinstance(value, dict) or not value:
            self.error(
                path,
                "必须是 ECharts option 对象",
                '如 {"xAxis": {"type": "category"}, "series": [{"type": "bar", "data": [...]}]}',
            )
            return
        try:
            size = len(json.dumps(value, ensure_ascii=False))
        except (TypeError, ValueError):
            self.error(path, "含有无法序列化的值（函数 / 自定义对象）")
            return
        if size > MAX_CHART_OPTION_CHARS:
            self.error(
                f"{path}（约 {size} 字符）",
                f"超过上限 {MAX_CHART_OPTION_CHARS}",
                "面板里的图表是给结论配的图；数据量大请用工具导出成文件",
            )

    def _check_graph_ir(self, path: str, value: Any) -> None:
        """Graph.ir：**直接复用** `render_graph` 的校验器，不写第二份规则。

        图与面板两条通道必须对同一份 IR 给出同一个结论，否则会出现
        "render_graph 通过、塞进面板却渲染不出来"的割裂。
        """
        if not isinstance(value, dict):
            self.error(path, "必须是 GraphIR 对象（与 render_graph 的入参同形态）")
            return
        result = validate_graph_ir(value)
        if result.ok:
            return
        for issue in result.issues[:MAX_GRAPH_IR_ERRORS]:
            self.error(
                f"{path}（GraphIR {issue.path}）",
                f"图形规格校验未过：{issue.message}",
                issue.hint,
            )
        if len(result.issues) > MAX_GRAPH_IR_ERRORS:
            self.error(
                path,
                f"另有 {len(result.issues) - MAX_GRAPH_IR_ERRORS} 处图形规格问题未列出",
                "最省事的做法：先单独调 render_graph 把 IR 调通，再把它放进面板",
            )

    def _check_file_items(self, path: str, value: Any) -> None:
        if not isinstance(value, list) or not value:
            self.error(path, "必须是非空数组", "每项 {name, path?, size?}")
            return
        if len(value) > MAX_FILE_ITEMS:
            self.error(
                f"{path}（{len(value)} 项）",
                f"超过上限 {MAX_FILE_ITEMS} 项",
                "面板不是文件管理器；更多文件请让用户在工作区面板查看",
            )
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                self.error(item_path, "每一项必须是对象 {name, path?, size?}")
                continue
            unknown = [k for k in item if k not in ("name", "path", "size")]
            if unknown:
                self.error(item_path, "包含不认识的字段：" + ", ".join(sorted(unknown)))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                self.error(f"{item_path}.name", "缺少 name（文件名，用于展示与择图标）")
            size = item.get("size")
            if size is not None and (
                isinstance(size, bool) or not isinstance(size, (int, float))
            ):
                self.error(f"{item_path}.size", "size 应为字节数（数字）")
            self._check_relative_path(f"{item_path}.path", item.get("path"))

    def _check_relative_path(self, path: str, value: Any) -> None:
        """工作区相对路径：禁绝对路径、禁 ``..`` 上跳。空值不报（由必填分支负责）。"""
        if not isinstance(value, str) or not value:
            return
        if value.startswith("/") or ".." in value.split("/"):
            self.error(
                f"{path} = {value!r}",
                "工作区路径不允许绝对路径或 .. 上跳",
                "请用相对工作区的路径，如 output/report.pdf",
            )

    # -- 图结构 ---------------------------------------------------------
    def _check_root(self) -> None:
        if ROOT_ID not in self.by_id:
            self.error(
                "components",
                f"缺少 id 为 {ROOT_ID!r} 的根组件",
                "每块面板必须有且仅有一个 root，其它组件从 root 可达",
            )

    def _check_references(self) -> None:
        declared = set(self.by_id)
        near = ", ".join(sorted(declared)[:12])
        for path, ids in self.ref_paths:
            for target in ids:
                if target not in declared:
                    self.error(
                        f"{path} 引用了不存在的组件 id {target!r}",
                        "引用必须指向已声明的组件",
                        f"已声明 id：{near}",
                    )

    def _check_unreachable(self) -> None:
        seen: set[str] = set()
        stack = [ROOT_ID] if ROOT_ID in self.by_id else []
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(t for t in self.children_of.get(node, ()) if t in self.by_id)
        self.reachable = seen
        orphans = [cid for cid in self.order if cid not in seen]
        if orphans:
            self.warn(
                "components",
                f"有 {len(orphans)} 个组件从 root 不可达，已忽略："
                + ", ".join(orphans[:12]),
                "不可达组件不会渲染；请把它们挂进 root 的 children",
            )

    def _check_cycles_and_depth(self) -> None:
        # state: 1=在递归栈上 2=已完成
        state: dict[str, int] = {}
        self._cycle_found = False

        def walk(node: str, stack: list[str]) -> None:
            state[node] = 1
            if len(stack) + 1 > MAX_DEPTH:
                self.error(
                    f"components[{self.order.index(node)}]"
                    f"（{self.by_id[node].get('component')}）",
                    f"嵌套深度 {len(stack) + 1} 超过上限 {MAX_DEPTH}",
                    "请减少层级，或把子树拆成独立面板",
                )
                state[node] = 2
                return
            for child in self.children_of.get(node, ()):
                if state.get(child) == 1:
                    self.error(
                        f"components[{self.order.index(child)}]",
                        "检测到环：" + " → ".join(stack + [node, child]),
                        "组件引用必须是一棵树，不能成环",
                    )
                    continue
                if state.get(child) is None:
                    walk(child, stack + [node])
            state[node] = 2

        for node in self.order:
            if state.get(node) is None:
                walk(node, [])

    def _check_rich_media(self) -> None:
        heavy = [
            cid
            for cid in self.by_id
            if self.by_id[cid].get("component") in RICH_MEDIA_COMPONENTS
        ]
        if len(heavy) > MAX_RICH_MEDIA:
            self.error(
                "components",
                f"同屏重组件（Chart/Graph）{len(heavy)} 个，超过上限 {MAX_RICH_MEDIA}",
                "重组件会显著拖慢滚动（044 §16.2）；请拆成多次 render_ui 调用",
            )
        # 单类限额：Chart 与 Graph 都属高成本项，各只允许 1 个。
        # 这条比总量上限更严——「1 Chart + 1 Graph」合规，「2 Chart」不合规。
        for kind, limit in (("Chart", MAX_CHART), ("Graph", MAX_GRAPH)):
            count = sum(
                1 for cid in self.by_id if self.by_id[cid].get("component") == kind
            )
            if count > limit:
                self.error(
                    "components",
                    f"{kind} 组件 {count} 个，超过上限 {limit}",
                    "一块面板最多放一个同类重组件；多图请拆成多次 render_ui 调用",
                )

    # -- 产出 -----------------------------------------------------------
    @staticmethod
    def _strip_chart_theme(option: dict[str, Any]) -> dict[str, Any]:
        """剥掉 Chart.option **顶层**的展示性键（044 §9.4）。

        深浅色必须由前端 theme 决定，后端不参与配色。**是剥掉不是报错**：
        模型写配色属于"多此一举"而非"参数错误"，报错只会白烧一轮往返，
        剥掉能让产出稳定收敛到统一主题。只动顶层——继续深挖
        ``series[].itemStyle`` 会把"props 转发"做成"第二套主题引擎"。
        """
        dropped = [key for key in option if key in CHART_OPTION_DROPPED_KEYS]
        if not dropped:
            return option
        return {k: v for k, v in option.items() if k not in CHART_OPTION_DROPPED_KEYS}

    def normalized(self) -> dict[str, Any]:
        """裁剪后的最终 IR：去掉不可达组件与未知键，其余原样保留。"""
        keep = self.reachable or set(self.by_id)
        components: list[dict[str, Any]] = []
        for cid in self.order:
            if cid not in keep:
                continue
            raw = self.by_id[cid]
            kind = str(raw["component"])
            item: dict[str, Any] = {"id": cid, "component": kind}
            for name in COMPONENTS[kind]["props"]:
                if name not in raw:
                    continue
                value = raw[name]
                if kind == "Chart" and name == "option" and isinstance(value, dict):
                    value = self._strip_chart_theme(value)
                item[name] = value
            components.append(item)
        out: dict[str, Any] = {
            "surfaceId": self.surface.get("surfaceId"),
            "components": components,
            "data": self.data,
        }
        title = self.surface.get("title")
        if isinstance(title, str) and title.strip():
            out["title"] = title.strip()
        declared = self.surface.get("actions")
        if isinstance(declared, list):
            out["actions"] = [
                name
                for name in declared
                if isinstance(name, str) and name not in BUILTIN_ACTIONS
            ]
        return out


def validate_ui_surface(surface: Any, *, catalog_id: str | None = None) -> UiValidation:
    """校验中立 IR。失败时不产出 ``normalized``（调用方应据此硬报错）。"""
    if not isinstance(surface, dict):
        return UiValidation(
            ok=False,
            errors=[
                UiIssue("<surface>", "必须是对象", "形如 {surfaceId, components, data}")
            ],
        )
    validator = _SurfaceValidator(surface, catalog_id)
    validator.check_top_level()
    validator.check_components()
    if validator.errors:
        return UiValidation(ok=False, errors=validator.errors, warnings=validator.warnings)
    return UiValidation(
        ok=True,
        normalized=validator.normalized(),
        errors=[],
        warnings=validator.warnings,
    )
