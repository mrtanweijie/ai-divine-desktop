"""A2UI catalog — Divine 自有组件目录的**唯一真源**。

设计文档：``docs/design/028-a2ui-integration-20261009.md`` §4。

本模块只放「事实」：组件名、每个组件的属性表、限额、tone 集合、action 规则。
两个消费方：

1. ``validator.py`` —— 读这里做校验与「合法枚举回灌」；
2. ``scripts/gen_ui_catalog.py`` —— 由这里生成 ``divine_catalog.json``。

前端 ``divine-app/src/pages/chat/components/UISurface/types.ts`` **手工镜像**
本模块（不共享代码，跨语言），靠 ``tests/test_render_ui.py`` 的快照锁死形态。
这与 GraphIR 完全同范式：``app/tools/graph/schema.py`` ↔ ``GraphBlock/GraphIR.ts``。

**设计原则（沿用 044 §2.3）**：IR 只描述「展示什么 + 能做什么」，
不描述「长什么样」—— 禁坐标、禁色值、禁样式、禁 HTML/脚本。
视觉一律由前端组件与设计 token 决定。
"""

from __future__ import annotations

from typing import Any, Sequence

# ---------------------------------------------------------------------------
# 协议基线
# ---------------------------------------------------------------------------

#: 对齐的 A2UI 规范版本。v1.0 仍是候选，升级只改 ``versions/`` 下的模块。
A2UI_VERSION = "v0.9.1"

#: 本机稳定标识（§14 待决 4：暂用本地 URL，等有外部消费方再迁公网）。
CATALOG_ID = "https://divine.local/catalogs/divine-ui/v0_9_1.json"

# ---------------------------------------------------------------------------
# 闭集枚举
# ---------------------------------------------------------------------------

#: 语义色。**只允许语义，不允许色值**——深浅色由前端 theme 决定（044 §9.4）。
TONES: tuple[str, ...] = ("default", "primary", "success", "warning", "danger")

GAPS: tuple[str, ...] = ("none", "sm", "md", "lg")
ALIGNS: tuple[str, ...] = ("start", "center", "end", "stretch")
JUSTIFIES: tuple[str, ...] = ("start", "center", "end", "between")
TEXT_VARIANTS: tuple[str, ...] = ("h1", "h2", "h3", "h4", "body", "caption")
BUTTON_VARIANTS: tuple[str, ...] = ("primary", "ghost", "danger")
ORIENTATIONS: tuple[str, ...] = ("horizontal", "vertical")
STEP_STATUSES: tuple[str, ...] = ("pending", "active", "done", "error")

GROUP_LABELS: dict[str, str] = {
    "layout": "布局",
    "display": "展示",
    "input": "输入",
    "action": "动作",
    "media": "富媒体",
}

# ---------------------------------------------------------------------------
# 限额（validator 硬拒，超限报错让模型拆成多次调用）
# ---------------------------------------------------------------------------

MAX_COMPONENTS = 120
MAX_DEPTH = 12
#: 重组件同屏上限（Chart + Graph 合计，044 §4.3）。
MAX_RICH_MEDIA = 2
#: 单类重组件上限（各 1 个）：Chart 与 Graph 都属高成本项（044 §4.3）。
MAX_CHART = 1
MAX_GRAPH = 1
MAX_TABLE_ROWS = 200
#: FileList 的条目上限。面板不是文件管理器，超出请让用户去工作区面板看。
MAX_FILE_ITEMS = 50
MAX_ACTIONS = 8
#: Chart.option 序列化后的字符上限，只兜底病态 payload。
MAX_CHART_OPTION_CHARS = 40_000
#: 序列化后字符数上限，只兜底病态 payload（组件数已封顶）。
MAX_SURFACE_CHARS = 200_000

# ---------------------------------------------------------------------------
# Action 规则（044 §8.2）
# ---------------------------------------------------------------------------

#: 内置动作：任何面板都可以用（提交 / 取消 / 刷新 / 收起 / 打开）。
BUILTIN_ACTIONS: tuple[str, ...] = ("submit", "cancel", "refresh", "dismiss", "open")

#: 业务动作（如 recalc / export_pdf）不允许模型临时发明：
#: 必须在 ``surface.actions`` 里登记，且名字符合本模式。
ACTION_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,31}$"

# ---------------------------------------------------------------------------
# 结构常量
# ---------------------------------------------------------------------------

#: 中立 IR 顶层允许的字段。
SURFACE_TOP_KEYS: tuple[str, ...] = (
    "surfaceId",
    "title",
    "components",
    "data",
    "actions",
)

#: 组件对象里除属性外的保留键（``component`` 是组件类型名）。
COMPONENT_RESERVED_KEYS: tuple[str, ...] = ("id", "component")

#: 数据绑定的唯一形式：``{"path": "/a/b"}``（RFC 6901 JSON Pointer 子集）。
BINDING_KEY = "path"

#: 需要计入「重组件」限额的组件（S5 接入，先占位）。
RICH_MEDIA_COMPONENTS: frozenset[str] = frozenset({"Chart", "Graph"})

#: Chart.option **顶层**会被剥掉的展示性键（044 §9.4：深/浅色由前端 theme 决定，
#: 后端不参与）。剥掉而不是报错——模型写配色是"多此一举"而非"参数错误"，
#: 报错只会浪费一轮往返；剥掉能让产出稳定收敛到统一主题。
#: 只剥顶层：继续深挖 `series[].itemStyle` 会把"props 转发"变成"第二套主题引擎"。
CHART_OPTION_DROPPED_KEYS: frozenset[str] = frozenset(
    {
        "color",
        "backgroundColor",
        "textStyle",
        "darkMode",
        "animation",
        "animationDuration",
        "animationEasing",
        "animationDelay",
        "media",
    }
)


def _p(
    type_: str,
    *,
    required: bool = False,
    enum: Sequence[str] = (),
    bindable: bool = False,
    default: Any = None,
    desc: str = "",
) -> dict[str, Any]:
    """声明一个组件属性。

    ``type_`` 取值与 validator 的分支一一对应：

    - ``string`` / ``integer`` / ``number`` / ``boolean`` —— 标量字面量；
      ``bindable=True`` 时也接受 ``{"path": "/x"}``。
    - ``children`` —— 子组件 id 列表；``child`` —— 单个子组件 id。
    - ``options`` / ``columns`` / ``steps`` —— 定形数组。
    - ``action`` —— 动作对象 ``{name, context?}``。
    """
    spec: dict[str, Any] = {
        "type": type_,
        "required": required,
        "bindable": bindable,
        "description": desc,
    }
    if enum:
        spec["enum"] = list(enum)
    if default is not None:
        spec["default"] = default
    return spec


# ---------------------------------------------------------------------------
# 组件目录 —— 首批 18 个（布局 4 / 展示 6 / 输入 7 / 动作 1）
# ---------------------------------------------------------------------------

COMPONENTS: dict[str, dict[str, Any]] = {
    # ---------------- A 组 · 布局 ----------------
    "Column": {
        "group": "layout",
        "label": "纵向容器",
        "props": {
            "children": _p("children", required=True, desc="子组件 id 列表，顺序即渲染顺序"),
            "gap": _p("string", enum=GAPS, default="md"),
            "align": _p("string", enum=ALIGNS, default="stretch"),
            "justify": _p("string", enum=JUSTIFIES, default="start"),
        },
    },
    "Row": {
        "group": "layout",
        "label": "横向容器",
        "props": {
            "children": _p("children", required=True, desc="子组件 id 列表"),
            "gap": _p("string", enum=GAPS, default="sm"),
            "align": _p("string", enum=ALIGNS, default="center"),
            "wrap": _p("boolean", default=False, desc="超宽是否换行"),
        },
    },
    "Card": {
        "group": "layout",
        "label": "卡片容器",
        "props": {
            "child": _p("child", required=True, desc="内容组件 id（单个）"),
            "title": _p("string", bindable=True, desc="卡片标题（可选）"),
            "tone": _p("string", enum=TONES, default="default"),
        },
    },
    "Divider": {
        "group": "layout",
        "label": "分隔线",
        "props": {
            "orientation": _p("string", enum=ORIENTATIONS, default="horizontal"),
        },
    },
    # ---------------- B 组 · 展示 ----------------
    "Text": {
        "group": "display",
        "label": "文本",
        "props": {
            "text": _p(
                "string",
                required=True,
                bindable=True,
                desc="纯文本；**不解析 HTML/Markdown**（富文本走正文的 MarkdownView）",
            ),
            "variant": _p("string", enum=TEXT_VARIANTS, default="body"),
            "tone": _p("string", enum=TONES, default="default"),
        },
    },
    "Badge": {
        "group": "display",
        "label": "徽标",
        "props": {
            "text": _p("string", required=True, bindable=True),
            "tone": _p("string", enum=TONES, default="default"),
        },
    },
    "Image": {
        "group": "display",
        "label": "图片",
        "props": {
            "url": _p(
                "string",
                required=True,
                desc="仅 http(s) 或工作区相对路径；拒绝 .. / 绝对路径 / file: / data: / javascript:",
            ),
            "alt": _p("string", desc="无障碍描述，建议填写"),
            "aspectRatio": _p(
                "number",
                desc="宽高比（w/h）。**必填以预留高度**，防虚拟列表抖动（044 §16.4）",
            ),
            "caption": _p("string", bindable=True),
        },
    },
    "Table": {
        "group": "display",
        "label": "数据表",
        "props": {
            "columns": _p(
                "columns",
                required=True,
                desc="列定义 [{key, title, width?}]；key 对应行对象字段",
            ),
            "rows": _p(
                "array",
                required=True,
                bindable=True,
                desc=(
                    "行数据，**行对象数组**：每个元素是「列 key → 单元格值」的对象，"
                    '如 [{"field": "姓名", "value": "张三"}]，'
                    "**不要给二维数组**（[[\"姓名\",\"张三\"]]，前端按列 key 取值会全空）；"
                    f"**行数上限 {MAX_TABLE_ROWS}**，超出请改用 run_sql 之类工具导出文件"
                ),
            ),
            "maxHeight": _p("integer", desc="内部滚动高度（px），建议 ≤ 320"),
            "caption": _p("string", bindable=True),
        },
    },
    "Progress": {
        "group": "display",
        "label": "进度条",
        "props": {
            "value": _p("number", required=True, bindable=True, desc="0..1"),
            "label": _p("string", bindable=True),
            "tone": _p("string", enum=TONES, default="default"),
        },
    },
    "Steps": {
        "group": "display",
        "label": "步骤条",
        "props": {
            "items": _p(
                "steps",
                required=True,
                desc="步骤 [{label, status}]，status ∈ " + "|".join(STEP_STATUSES),
            ),
            "caption": _p("string", bindable=True),
        },
    },
    # ---------------- C 组 · 输入 ----------------
    "TextField": {
        "group": "input",
        "label": "单行输入",
        "props": {
            "label": _p("string", required=True),
            "value": _p("string", required=True, bindable=True, desc="绑定 data 里的路径"),
            "placeholder": _p("string"),
            "required": _p("boolean", default=False),
        },
    },
    "TextArea": {
        "group": "input",
        "label": "多行输入",
        "props": {
            "label": _p("string", required=True),
            "value": _p("string", required=True, bindable=True),
            "rows": _p("integer", default=4),
        },
    },
    "NumberField": {
        "group": "input",
        "label": "数字输入",
        "props": {
            "label": _p("string", required=True),
            "value": _p("number", required=True, bindable=True),
            "min": _p("number"),
            "max": _p("number"),
            "step": _p("number"),
            "unit": _p("string", desc="单位后缀，如 % / 万"),
        },
    },
    "Select": {
        "group": "input",
        "label": "下拉选择",
        "props": {
            "label": _p("string", required=True),
            "value": _p("string", required=True, bindable=True),
            "options": _p("options", required=True, desc="[{value, label}]"),
        },
    },
    "ChoicePicker": {
        "group": "input",
        "label": "选项卡片",
        "props": {
            "value": _p("string", required=True, bindable=True, desc="多选时用逗号分隔"),
            "options": _p("options", required=True, desc="[{value, label, desc?}]"),
            "multiple": _p("boolean", default=False),
        },
    },
    "Checkbox": {
        "group": "input",
        "label": "复选框",
        "props": {
            "label": _p("string", required=True),
            "checked": _p("boolean", required=True, bindable=True),
        },
    },
    "Switch": {
        "group": "input",
        "label": "开关",
        "props": {
            "label": _p("string", required=True),
            "checked": _p("boolean", required=True, bindable=True),
        },
    },
    # ---------------- D 组 · 动作 ----------------
    "Button": {
        "group": "action",
        "label": "按钮",
        "props": {
            "text": _p("string", required=True, bindable=True),
            "variant": _p("string", enum=BUTTON_VARIANTS, default="primary"),
            "disabled": _p("boolean", default=False),
            "action": _p(
                "action",
                required=True,
                desc=(
                    "动作 {name, context?}；name 必须是内置动作（"
                    + "|".join(BUILTIN_ACTIONS)
                    + "）或在 surface.actions 里登记过的业务动作"
                ),
            ),
        },
    },
    # ---------------- E 组 · 富媒体（S5） ----------------
    # 三个组件都**只做 props 转发**：图表交给 ChartBlock、关系图交给 GraphBlock、
    # 文件列表复用 ToolFileList 的行样式。**禁止第二套 ECharts/X6 代码**
    # （044 §4.2 的 S5 追加说明）。
    "Chart": {
        "group": "media",
        "label": "图表",
        "props": {
            "option": _p(
                "chartOption",
                required=True,
                desc=(
                    "ECharts option（与 generate_chart 的产物同形态）。"
                    "**不要写 color/backgroundColor/textStyle/animation**："
                    "深浅色由前端主题决定，写了也会被剥掉（044 §9.4）"
                ),
            ),
            "height": _p(
                "integer",
                default=260,
                desc="预留高度 px。**必须给足**，否则加载完会撑高、让虚拟列表滚动跳动",
            ),
            "caption": _p("string", bindable=True),
        },
    },
    "Graph": {
        "group": "media",
        "label": "关系图",
        "props": {
            "ir": _p(
                "graphIR",
                required=True,
                desc=(
                    "GraphIR（与 render_graph 同一份契约）。"
                    "最省事的办法是直接复用 render_graph 那次调用里已经通过的 IR"
                ),
            ),
            "height": _p("integer", default=320, desc="预留高度 px；X6 异步创建，必须自留高度"),
            "caption": _p("string", bindable=True),
        },
    },
    "FileList": {
        "group": "media",
        "label": "文件列表",
        "props": {
            "files": _p(
                "fileItems",
                required=True,
                desc=(
                    f"文件项 [{{name, path?, size?}}]，**上限 {MAX_FILE_ITEMS} 项**。"
                    "path 为工作区内相对路径（禁绝对路径与 ..）；"
                    "图标按 name 的扩展名自动选，不必自己指定"
                ),
            ),
            "caption": _p("string", bindable=True),
        },
    },
}

COMPONENT_NAMES: tuple[str, ...] = tuple(COMPONENTS)


def components_by_group() -> dict[str, list[str]]:
    """按组返回组件名，供工具描述与 catalog JSON 生成。"""
    out: dict[str, list[str]] = {group: [] for group in GROUP_LABELS}
    for name, spec in COMPONENTS.items():
        out.setdefault(str(spec["group"]), []).append(name)
    return out


def component_hint() -> str:
    """一行一组的组件速查，用于工具 DESCRIPTION（不列属性，省 token）。"""
    by_group = components_by_group()
    return "；".join(
        f"{GROUP_LABELS[group]}：{'/'.join(by_group.get(group) or [])}"
        for group in GROUP_LABELS
    )


def catalog_document() -> dict[str, Any]:
    """生成 ``divine_catalog.json`` 的内容（产物，不是真源）。"""
    return {
        "catalogId": CATALOG_ID,
        "a2uiVersion": A2UI_VERSION,
        "groups": GROUP_LABELS,
        "limits": {
            "maxComponents": MAX_COMPONENTS,
            "maxDepth": MAX_DEPTH,
            "maxRichMedia": MAX_RICH_MEDIA,
            "maxChart": MAX_CHART,
            "maxGraph": MAX_GRAPH,
            "maxTableRows": MAX_TABLE_ROWS,
            "maxFileItems": MAX_FILE_ITEMS,
            "maxActions": MAX_ACTIONS,
            "maxChartOptionChars": MAX_CHART_OPTION_CHARS,
            "maxSurfaceChars": MAX_SURFACE_CHARS,
        },
        "actions": {
            "builtin": list(BUILTIN_ACTIONS),
            "namePattern": ACTION_NAME_PATTERN,
        },
        "tones": list(TONES),
        "components": {
            name: {
                "group": spec["group"],
                "label": spec["label"],
                "props": spec["props"],
            }
            for name, spec in COMPONENTS.items()
        },
    }
