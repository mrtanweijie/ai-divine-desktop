import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.scripts.file_utils import unique_output_path  # noqa: E402
from app.pdf_tool import PDFTool  # noqa: E402


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".pdf"):
        cleaned += ".pdf"
    return cleaned


async def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}
    prompt = str(params.get("prompt") or params.get("content") or "").strip()
    if not prompt:
        print(
            json.dumps(
                {"success": False, "message": "缺少 prompt"},
                ensure_ascii=False,
            )
        )
        return

    output_dir = output_root / "pdf"
    raw_path = str(params.get("path") or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        output_dir = candidate.resolve()
        try:
            output_dir.relative_to(workspace.resolve())
        except ValueError:
            print(
                json.dumps(
                    {"success": False, "message": f"保存路径越界: {output_dir}"},
                    ensure_ascii=False,
                )
            )
            return
    output_dir.mkdir(parents=True, exist_ok=True)

    from app.pdf_tool.intent import _clean_title

    file_name = str(params.get("file_name") or "").strip()
    if not file_name:
        file_name = _clean_title(prompt) or prompt[:40]
    file_name = re.sub(r"\.md$", "", file_name, flags=re.IGNORECASE)
    output_path = unique_output_path(output_dir, file_name, "PDF文档", ".pdf")
    try:
        meta = await PDFTool().run(
            prompt,
            output_path,
            kind=str(params.get("kind") or "").strip() or None,
            style=str(params.get("style") or "").strip() or None,
            theme=str(params.get("theme") or "").strip() or None,
            color_scheme=str(params.get("color_scheme") or "").strip() or None,
            paper_size=str(params.get("paper_size") or "A4").strip(),
            cover=bool(params.get("cover")),
            toc=bool(params.get("toc")),
            base_dir=workspace,
            content=str(params.get("markdown") or "").strip() or None,
            resume_data=params.get("resume_data") or None,
            color_overrides=params.get("theme_colors") or None,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": f"PDF 生成失败: {exc}",
                    "messageKey": "tool.actionFailed",
                },
                ensure_ascii=False,
            )
        )
        return
    print(
        json.dumps(
            {
                "success": True,
                "message": "PDF 文档生成完成",
                "file_name": output_path.name,
                "filepath": str(output_path),
                "data": {
                    "recipe": meta.get("recipe"),
                    "display_name": meta.get("display_name"),
                    "theme": meta.get("theme"),
                    "title": meta.get("title"),
                    "renderer": meta.get("renderer"),
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
