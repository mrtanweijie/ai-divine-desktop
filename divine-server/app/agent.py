from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from . import db
from .rag_store import (
    index_workspace as rag_index_workspace,
    search_workspace as rag_search_workspace,
)
from .tools.base import ToolExecutionError

logger = logging.getLogger("divine.agent")


def _summarize_arguments(arguments: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > 80:
            parts.append(f"{key}={len(value)}chars")
        else:
            parts.append(f"{key}={value!r}")
    return ", ".join(parts)[:500]


_PLAN_STATUS_LABELS = {
    "pending": "待办",
    "running": "执行中",
    "done": "完成",
    "error": "失败",
    "skipped": "跳过",
}

_RAG_KEYWORDS = (
    "笔记",
    "文件",
    "文档",
    "目录",
    "资料",
    "章节",
    "大纲",
    "小说",
    "续写",
    "内容",
    "方案",
    "工作区",
    "里面",
    "之前",
)


def _auto_rag_context(
    history: list[dict[str, Any]], workspace: Any
) -> str | None:
    question = next(
        (
            message.get("content", "")
            for message in reversed(history)
            if message.get("role") == "user"
        ),
        "",
    )
    question = (question or "").strip()
    if not question:
        return None
    try:
        results = rag_search_workspace(workspace, question, 3)
        if not results and any(
            keyword in question for keyword in _RAG_KEYWORDS
        ):
            rag_index_workspace(workspace)
            results = rag_search_workspace(workspace, question, 3)
    except Exception:
        return None
    if not results:
        return None
    blocks = [
        f"[{result['file_path']}]\n{result['snippet']}"
        for result in results
    ]
    return (
        "以下是工作区本地资料检索结果：\n\n"
        + "\n\n".join(blocks)
        + "\n\n请优先结合这些资料回答用户问题。"
    )


def _plan_progress(todos: list[dict[str, Any]]) -> str:
    if not todos:
        return ""
    total = len(todos)
    done = sum(1 for todo in todos if todo["status"] == "done")
    lines = [f"当前计划进度：{done}/{total}"]
    for index, todo in enumerate(todos, start=1):
        label = _PLAN_STATUS_LABELS.get(todo["status"], todo["status"])
        lines.append(f"{index}. [{label}] {todo['title']}")
    return "\n".join(lines)


def _claim_next_todo(
    session_id: str, todos: list[dict[str, Any]]
) -> dict[str, Any] | None:
    for todo in todos:
        if todo["status"] == "pending":
            todo["status"] = "running"
            db.update_todo_status(todo["id"], "running")
            return todo
    return None


def _finish_todo(
    todo: dict[str, Any] | None, success: bool, message: str = ""
) -> None:
    if todo is None:
        return
    status = "done" if success else "error"
    todo["status"] = status
    db.update_todo_status(todo["id"], status, (message or "")[:500])


SYSTEM_PROMPT = """你是 AI Divine，一个本地优先的桌面 AI 助手。
你可以回答问题，也可以使用本地工具生成文件。生成文件前先向用户简要说明计划，
再选择最合适的工具。工具结果要结合到最终回答中，并告诉用户下载链接。
面对需要多步执行的复杂任务，先调用 write_todos 列出待办事项，再按待办顺序逐项执行；
不要跳过未完成事项，也不要重复执行已完成事项。
执行需要修改文件、生成文件或运行命令的任务前，先询问用户是否要出一份方案；
用户选择先出方案后，先调用 write_todos，不要直接执行其他工具。
不要输出 XML 或伪代码形式的工具调用；需要生成笔记时直接调用 notes 工具。
调用 notes 时必须提供明确、具体的标题，不要使用“未命名笔记”作为标题。
生成笔记时若用户指定目录，使用 notes 的 path 参数传入 workspace 内相对目录，默认保存在 notes。
用户要求保存时，如果未明确指定格式，默认只生成 Markdown 笔记，不要同时生成多个格式的文件；
只有用户明确要求两种或更多格式时才生成多个。
当用户附加图片时，只能调用 read_image 分析当前消息中列出的图片附件，并使用该附件
给出的图片本地路径；不要使用历史消息中的图片路径，也不要对非图片文件调用 read_image。
read_image 返回的 content 就是图片识别结果，请基于它回答用户。
回答使用简洁的 Markdown，不输出与任务无关的内容。
重要规则：不要在正文中输出 download_url、/api/files/ 或 http://localhost 等文件链接；
生成文件后只需说明文件名和内容概要，文件下载/打开由前端工具卡片展示。
生成文件默认保存到应用输出目录，不写入当前项目/工作区；
只有用户明确要求保存到项目内时，才使用 path 参数指定 workspace 内相对目录。
修改已有源码、配置或文档必须使用 edit_files，一次调用传入所有文件的
SEARCH/REPLACE，不要逐个文件调用；修改前先在正文中列出将要修改的文件
和每个文件的改动点。SEARCH 必须与文件现有内容完全一致（含缩进、空行
和结尾换行），找不到时先用 read_file 查看文件内容再重试，不要改写其他位置。
创建新文件使用 edit_files 且 search 传空字符串，或用 write_file 写入完整内容。
自动创建父目录；默认禁止用 terminal heredoc 写文件，
除非用户明确要求使用终端方式。
## 代码修改
- 修改任何代码前，先列出将要修改的文件，并说明每个文件的改动内容。
- 所有改动必须一次性通过 `edit_files` 批量完成，不要逐个文件修改。
- 使用 SEARCH/REPLACE 块：
  - SEARCH 必须是文件中存在的精确文本，包含缩进和空白。
  - SEARCH 文本必须完整复制原文件内容，不能省略、不能添加注释、不能改变缩进。
  - 如果文本太长，只复制要修改的函数体或代码块，不要包含整个文件。
  - REPLACE 是替换后的内容。
  - 创建新文件时 SEARCH 传空字符串 `""`。
  - 一次调用可包含多个文件的改动。
只能调用本次请求提供的工具，不要杜撰未提供的工具名。
用户提到从 Claude Code、Qoder、Cursor 等工具迁移或导入技能时，
先调用 discover_importable_skills 扫描可迁移候选并向用户展示，
用户确认后调用 migrate_skill 或 migrate_skills；
迁移多个技能时必须一次性调用 migrate_skills，不要逐个调用 migrate_skill；
已存在的同名技能会自动跳过，不需要单独报错；
这两类工具执行前系统都会再次请求确认。
用户给出 GitHub 仓库地址想安装技能时，先调用 preview_skill_repo 拉取并展示
SKILL.md，用户确认后再调用 install_skill；install_skill 执行前系统会再次确认。
查找或列出工作区文件使用 search_files；搜索完文件后，读取具体内容再使用 read_file。
查看目录结构使用 directory_tree；缩放图片使用 image_resize；拆分合并 PDF 使用 pdf_split_merge；
用户要求生成 PDF 文档时，先向用户展示下面的风格编号表并询问偏好，不要直接调用 pdf_generate；
| 编号 | 风格 | theme |
| --- | --- | --- |
| 1 | 通用现代 | universal |
| 2 | Notion 极简 | notion |
| 3 | Linear 紧凑 | linear |
| 4 | Apple 舒适 | apple |
| 5 | 现代科技 | modern |
| 6 | 学术典雅 | academic |
| 7 | 旅行暖橙 | travel |
| 8 | 知识图谱 | roadmap |
| 9 | 极简黑白 | minimal |
| 10 | 个人简历 | resume |
用户回复编号即可，例如回复“1”；Agent 收到编号后按上表映射 theme，再调用 pdf_generate；
用户说“随便/默认/你来定”时使用 universal；
用户已明确指定编号或风格时不要重复询问。
用户要求生成 Word 文档时，同样先展示上面的风格编号表并询问偏好，不要直接调用 word_document；
用户回复编号后按上表映射 theme，再调用 word_document；已明确指定风格时不要重复询问。
用户要求生成 PPT/演示文稿时，同样先展示上面的风格编号表并询问偏好，不要直接调用 presentation；
用户回复编号后按上表映射 theme，再调用 presentation；已明确指定风格时不要重复询问。
PPT 内容页可用 layout=cards/timeline/columns 指定版式，不传时工具会自动判断；
阶段/路线类标题优先时间轴，要点较多时用卡片，少量要点时分栏。
kind 按报告/旅游攻略/学习路线/电子书手册/讲义/简历自动识别或显式指定；
用户要求生成个人简历时，按一页简历数据结构整理 resume_data：
name（姓名）、target（目标岗位）、contact（可传 "电话 | 邮箱 | 网站" 或对象）、
summary（1-2 行职业摘要）、core_skills（6-12 个核心技能关键词）、
work（[{company, position, period, points[2-4 条成果]}]）、
projects（[{name, role, context(一句话背景), points[2-4 条成果]}]）、
education（[{school, degree, period}]）；
也兼容 basics、experience、startDate/endDate、level 1-5 等常见简历字段；
整理完成后再调用 pdf_generate，传 kind=resume 和 resume_data；
resume_data 的字段结构只是规范示例，具体内容必须根据用户实际信息生成，
不要套用示例简历内容；用户信息不足时先询问姓名、目标岗位、工作经历、技能。
不要要求用户填写复杂表单，关键信息缺失时简单询问姓名、目标职位、工作经历、技能即可；
简历主题可选 professional/creative/minimal/boss_zhipin/finance/linkedin/kami/kami_white，用户未指定时默认 professional。
场景推荐：BOSS 直聘/招聘平台/ATS/海投 → boss_zhipin；
Kami/Resume Optimizer 风格/排版优化 → kami；
Kami 纯白/白色投递版 → kami_white；
LinkedIn/海外投递 → linkedin；金融/银行/投行/证券/基金/财务/审计 → finance；
投大厂/外企/传统行业 → professional；
互联网/创业/设计岗/内推 → creative；学术/咨询/法律/科研 → minimal；
用户未说明求职场景时，可先询问目标场景再选主题。
整理简历内容遵循简历优化规范：把职责描述改成成果描述；每条经历保留 2-4 条高密度 bullet；
bullet 使用“动作 + 产物 + 结果”结构；有量化数据优先写数字，没有精确数字时写范围/频率/流程变化；
严禁编造指标、头衔或项目背景，缺失数据用“[量化数据待补]”占位；
每段项目先写一句背景（系统定位 + 服务对象 + 解决什么问题）再列 bullet；
技能只保留与目标岗位匹配的关键词；不强制限制页数，按实际内容控制信息密度；
用户明确要求一页版时，再按一页简历规则压缩。
不要把完整 Markdown 当 prompt 传入，除非用户已经提供现成内容；
如果只是把已有 Markdown 渲染成 PDF，才使用 pdf_render。
只读查询数据库使用 sqlite_query；数学计算使用 calculator；剪贴板操作使用 clipboard。
安排提醒或定时任务时调用 schedule_task；创建提醒后不要直接写日程，系统会询问用户是否写入日程，
用户确认后再调用 write_calendar，并把 task_id 传给 write_calendar。
用户要求记录日程/日历事件时调用 write_calendar，可单独使用，从用户输入中识别标题和起止时间。
本地资料检索使用 rag_index 建立索引、rag_search 检索相关内容。
用户要求查看/绘制/输出流程图、时序图、架构图时，直接在正文输出 ```mermaid ... ```
代码块，前端会自动渲染；不要调用 mermaid_export，也不要生成文件。
只有用户明确要求保存/导出/下载为 .mmd 文件时，才调用 mermaid_export，
content 传 Mermaid 源码（不要带围栏代码块）。
用户要求生成/绘制 SVG 矢量图、图标、插画、角色或自定义图形时，按以下规则执行：
- 首轮从零生成使用 draw_svg，content 传完整合法 SVG 源码（以 <svg 开头，不要带围栏代码块）；
  后续修改必须使用 edit_svg，不要重新生成；需要先理解当前 SVG 时可用 describe_svg；
  用户说“导出/转 PNG/我要位图”时使用 svg_to_png；
  用户要 iOS/Android 多尺寸图标或一次导出多个 PNG 尺寸时，使用 svg_to_png_batch，
  一次性传入 sizes 列表，不要逐个调用 svg_to_png。
- edit_svg 的 file_path 传当前 SVG 文件路径，content 传完整更新后的 SVG 源码；
  只改用户指令中提到的元素，其他元素、属性、层级和顺序保持原样。
- 处理 SVG 时不要先说明计划；生成或编辑 SVG 的正文不要加解释，也不要写“生成完成”等说明，只输出 SVG 代码；
  如果同时要展示给用户，直接在正文放 ```svg 代码块。
- 关键元素必须带简短、语义化、唯一的 id（如 eye-left、hair、body、head、arm-left），
  方便后续按 id 精确修改；不要使用外部图片，所有图形用 SVG 基本元素绘制。
- 用户要求的是趋势/对比/占比/分布等数据图表时仍使用 generate_chart，不要调用 draw_svg。
用户要求把需求文档/PRD 实现成交互式产品界面、UX 交互原型、可点击演示页面时，
必须先询问用户偏好的交互风格，不要默认生成任何 HTML；
风格只能从以下选项中选择：
1）Notion 风格：极简、留白多、适合阅读与轻量编辑；
2）Linear 风格：紧凑、信息密度高、偏研发协作；
3）Apple 风格：圆角大、阴影淡、视觉舒适；
4）纯文本 + 表单：无装饰，适合导出与打印；
5）自定义：用户自行描述偏好。
用户未明确选择时继续询问，不要调用 ux_html；
用户选择后，先分析文档，自行设计贴合产品形态和所选风格的 HTML/CSS/JS 交互页面，
再调用 ux_html；style 传用户选择的风格（Notion/Linear/Apple/PlainText/Custom），
自定义风格时用 style_note 记录用户描述，content 传完整 HTML 源码（包含 DOCTYPE 或 <html>），
ux_html 默认保存到当前项目工作区 html/ 目录，不要额外传 path；只有用户指定保存目录时才传 path。
不要使用统一模板，不要在正文中输出 HTML 或 JS 代码。
生成的 UX HTML 必须符合以下视觉规范：
- 风格参考 Apple / Linear / Notion，留白充足、排版克制、视觉层级清晰，不堆叠装饰元素；
- 不使用渐变背景，不使用过重阴影；
- 设计 token：正文 #111827、辅助文字 #6B7280、背景 #FFFFFF 或 #F9FAFB，主色按所选风格自行定义；
- 圆角统一 10px，间距使用 16 的倍数（如 16/24/32/48）；
- 必须响应式、语义化、交互完整，避免横向滚动，关键控件需要有 hover/focus/active 状态。
当用户要求画图、展示趋势/对比/占比/分布等图表时，调用 generate_chart 生成 ECharts option；
根据数据特征选择图表类型（趋势用 line、对比用 bar、占比用 pie 且类别不超过 8 个、
分布用 scatter、多指标用 bar + line 组合），option 必须完整合法且 series 非空，
不要在正文输出 HTML、JS 或图表代码。
读取文件内容必须使用 read_file、word_document 等专用工具；
读取大文件时使用 read_file 的 start_line/end_line 只读取需要的行段；
读取 Excel 必须使用 read_file（不要使用 spreadsheet，spreadsheet 只能生成 Excel）；
默认禁止用 terminal 执行 cat、python、openpyxl、find 等命令来读取或分析文件；
如果用户明确要求，可提交终端确认后执行。
需要同时抓取多个网页或数据源（如多个指数、多个新闻源）时，
使用 web_fetch_batch 一次性传入 urls 列表，不要逐个重复调用 web_fetch。
读取工作区外的本地文件或图片需要用户确认。
terminal 只能用于系统操作，例如安装依赖、运行命令、管理进程或用户明确要求的终端命令。"""

_READ_ONLY_TOOLS = {
    "discover_importable_skills",
    "load_skill",
    "preview_skill_repo",
    "read_file",
    "read_image",
    "search_files",
    "directory_tree",
    "rag_search",
    "sqlite_query",
    "calculator",
    "web_fetch",
    "web_fetch_batch",
    "generate_chart",
    "describe_svg",
}

_NO_PLAN_TOOLS = {
    "discover_importable_skills",
    "install_skill",
    "migrate_skill",
    "migrate_skills",
    "preview_skill_repo",
    "schedule_task",
    "write_calendar",
    "draw_svg",
    "edit_svg",
    "svg_to_png",
    "svg_to_png_batch",
}

MAX_TOOL_TURNS = 64


_STATIC_TOOL_SUCCESS_KEYS = {
    "notes": "tool.notesCreated",
    "word_document": "tool.wordCreated",
    "presentation": "tool.presentationCreated",
    "spreadsheet": "tool.spreadsheetCreated",
    "pdf_generate": "tool.pdfGenerated",
    "pdf_render": "tool.pdfRendered",
    "read_image": "tool.imageAnalyzed",
    "calculator": "tool.calculationDone",
    "image_resize": "tool.imageResized",
    "mermaid_export": "tool.mermaidExported",
    "draw_svg": "tool.svgCreated",
    "edit_svg": "tool.svgUpdated",
    "describe_svg": "tool.svgDescribed",
    "svg_to_png": "tool.svgExportedPng",
    "ux_html": "tool.uxHtmlCreated",
    "generate_chart": "tool.chartGenerated",
    "terminal": "tool.commandDone",
    "rag_index": "tool.ragIndexed",
}


def _tool_success_message(
    name: str,
    output: dict[str, Any],
    arguments: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    key = _STATIC_TOOL_SUCCESS_KEYS.get(name)
    if name == "read_file":
        data = output.get("data") or {}
        params: dict[str, Any] = {
            "name": output.get("file_name") or "",
            "start": data.get("line_start"),
            "end": data.get("line_end"),
            "total": data.get("total_lines"),
        }
        has_range = (
            arguments.get("start_line") is not None
            or arguments.get("end_line") is not None
        )
        return (
            "tool.fileReadRange" if has_range else "tool.fileRead",
            params,
        )
    if name == "directory_tree":
        try:
            tree = json.loads(output.get("content") or "{}").get("tree") or []
        except (TypeError, json.JSONDecodeError):
            tree = []
        return "tool.directoryScanned", {"count": len(tree)}
    if name == "sqlite_query":
        try:
            rows = json.loads(output.get("content") or "{}").get("rows") or []
        except (TypeError, json.JSONDecodeError):
            rows = []
        return "tool.queryDoneRows", {"count": len(rows)}
    if name == "search_files":
        try:
            files = json.loads(output.get("content") or "[]")
        except (TypeError, json.JSONDecodeError):
            files = []
        return "tool.filesFound", {"count": len(files)}
    if name == "rag_search":
        try:
            results = json.loads(output.get("content") or "[]")
        except (TypeError, json.JSONDecodeError):
            results = []
        return (
            "tool.ragSearchResults",
            {"count": len(results)},
        )
    if name == "rag_index":
        try:
            indexed = json.loads(output.get("content") or "{}")
        except (TypeError, json.JSONDecodeError):
            indexed = {}
        return (
            "tool.ragIndexed",
            {
                "files": indexed.get("files", 0),
                "chunks": indexed.get("chunks", 0),
            },
        )
    if name == "web_fetch":
        return "tool.webFetched", {"url": output.get("url") or ""}
    if name == "web_fetch_batch":
        results = (output.get("data") or {}).get("results") or []
        success = sum(
            1 for item in results if isinstance(item, dict) and item.get("success")
        )
        return (
            "tool.webFetchedBatch",
            {"success": success, "total": len(results)},
        )
    if name == "svg_to_png_batch":
        results = (output.get("data") or {}).get("results") or []
        success = sum(
            1 for item in results if isinstance(item, dict) and item.get("success")
        )
        return "tool.svgExportedPngBatch", {"count": success}
    if name == "pdf_split_merge":
        action = str(arguments.get("action") or "").lower()
        if action == "merge":
            return "tool.pdfMerged", {}
        if arguments.get("pages"):
            return "tool.pdfPagesExtracted", {}
        return "tool.pdfSplit", {}
    if name == "clipboard":
        action = str(arguments.get("action") or "read").lower()
        return {
            "write": "tool.clipboardWritten",
            "clear": "tool.clipboardCleared",
            "read": "tool.clipboardRead",
        }.get(action, "tool.clipboardRead"), {}
    if name == "edit_files":
        files = (output.get("data") or {}).get("files") or []
        created = sum(
            1 for item in files if isinstance(item, dict) and item.get("action") == "created"
        )
        return (
            "tool.filesEdited",
            {"created": created, "modified": len(files) - created},
        )
    if name == "write_file":
        mode = str(arguments.get("mode") or "write").lower()
        return (
            "tool.fileAppended" if mode == "append" else "tool.fileWritten",
            {},
        )
    if key:
        return key, {}
    return None


def _annotate_tool_output(
    name: str,
    output: dict[str, Any],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if output.get("messageKey"):
        return output
    if not output.get("success"):
        return output
    localized = _tool_success_message(name, output, arguments)
    if not localized:
        return output
    annotated = dict(output)
    annotated["messageKey"], annotated["messageParams"] = localized
    return annotated


async def _execute_tool(
    session_id: str,
    adapter: Any,
    name: str,
    arguments: dict[str, Any],
    workspace: Any,
    locale: str | None = None,
) -> dict[str, Any]:
    run = db.add_tool_run(session_id, name, "start", arguments)
    started = time.monotonic()
    logger.info("tool start session=%s name=%s", session_id, name)
    logger.info(
        "tool args session=%s name=%s args=[%s]",
        session_id,
        name,
        _summarize_arguments(arguments),
    )
    try:
        result = await asyncio.wait_for(
            adapter.run(workspace, arguments, locale=locale or "zh-CN"),
            timeout=adapter.timeout,
        )
        output = result.as_dict()
        output = _annotate_tool_output(name, output, arguments)
        db.update_tool_run(run["id"], "done", output)
        logger.info(
            "tool done session=%s name=%s duration=%.2fs success=%s",
            session_id,
            name,
            time.monotonic() - started,
            output.get("success"),
        )
        return output
    except asyncio.TimeoutError:
        output = {
            "success": False,
            "message": f"工具执行超时（{adapter.timeout}s）",
            "messageKey": "tool.toolTimeout",
            "messageParams": {"timeout": adapter.timeout},
        }
        db.update_tool_run(run["id"], "error", output)
        logger.warning(
            "tool timeout session=%s name=%s duration=%.2fs timeout=%s",
            session_id,
            name,
            time.monotonic() - started,
            adapter.timeout,
        )
        return output
    except ToolExecutionError as exc:
        output = {
            "success": False,
            "message": str(exc),
            "messageKey": exc.message_key,
            "messageParams": exc.message_params or {},
        }
        if not output["messageKey"]:
            output.pop("messageKey")
        if not output["messageParams"]:
            output.pop("messageParams")
        db.update_tool_run(run["id"], "error", output)
        logger.warning(
            "tool error session=%s name=%s duration=%.2fs error=%s",
            session_id,
            name,
            time.monotonic() - started,
            exc,
        )
        return output
