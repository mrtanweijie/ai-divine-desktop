"""html_resume 工具：简历的可编辑 HTML 输出（职责单一，不产出 PDF）。

复用 12 套简历模板管线渲染：产出可编辑 HTML（浏览器打开点击即可改，
工具条可下载/打印）+ 纯净投递版 HTML。PDF 版由 pdf_generate 负责。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.scripts.file_utils import unique_output_path  # noqa: E402


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}
    resume_data = params.get("resume_data")
    if not isinstance(resume_data, dict) or not resume_data:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": "缺少 resume_data：请先按简历规则整理结构化数据再调用",
                    "messageKey": "tool.actionFailed",
                },
                ensure_ascii=False,
            )
        )
        return

    from app.docgen.resume.templates import render_template_resume
    from app.docgen.resume.templates.registry import TEMPLATE_REGISTRY, get_entry

    template = str(params.get("template") or "").strip() or "tpl_professional"
    if template not in TEMPLATE_REGISTRY:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": (
                        f"未知模板: {template}，可选: {', '.join(TEMPLATE_REGISTRY)}"
                    ),
                    "messageKey": "tool.actionFailed",
                },
                ensure_ascii=False,
            )
        )
        return

    layout = str(params.get("layout") or "single").strip() or "single"
    if layout not in ("single", "multi"):
        layout = "single"

    output_dir = output_root / "html"
    raw_path = str(params.get("path") or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        output_dir = candidate.resolve()
        try:
            output_dir.relative_to(workspace)
        except ValueError:
            print(
                json.dumps(
                    {"success": False, "message": f"保存路径越界: {output_dir}"},
                    ensure_ascii=False,
                )
            )
            return

    name = str(params.get("file_name") or "").strip()
    if not name:
        name = f"{resume_data.get('name') or '我的'}简历"
    name = re.sub(r"\.(html?|pdf)$", "", name, flags=re.IGNORECASE)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, name, "简历", ".html")

    try:
        files = render_template_resume(
            resume_data,
            str(output_path),
            template_id=template,
            layout=layout,
            output_format="html",
            color_scheme=str(params.get("color_scheme") or "").strip() or None,
            color_overrides=params.get("color_overrides") or None,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": f"简历 HTML 生成失败: {exc}",
                    "messageKey": "tool.actionFailed",
                },
                ensure_ascii=False,
            )
        )
        return

    entry = get_entry(template)
    editable_path = files[0] if files else str(output_path)
    clean_path = files[1] if len(files) > 1 else ""
    print(
        json.dumps(
            {
                "success": True,
                "message": (
                    f"简历 HTML 生成完成（{entry['display_name']} · "
                    f"{'多页' if layout == 'multi' else '单页'}）：含可编辑版与纯净投递版。"
                    "可编辑版用浏览器打开，点击任意文字即可修改，"
                    "页面工具条可下载修改后的 HTML 或一键导出 PDF。"
                ),
                "file_name": Path(editable_path).name,
                "filepath": editable_path,
                "data": {
                    "template": template,
                    "template_name": entry["display_name"],
                    "layout": layout,
                    "clean_filepath": clean_path,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
