import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def _resolve(workspace: Path, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = workspace / path
    return path.resolve()


def _parse_pages(spec: str, total: int) -> list[int]:
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", part)
        if not match:
            raise ValueError(f"页码格式无效: {part}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end > total or start > end:
            raise ValueError(f"页码越界: {part}")
        pages.extend(range(start, end + 1))
    return sorted(set(pages))


def _merge(workspace: Path, params: dict) -> None:
    files = params.get("files") or []
    if not files:
        raise ValueError("缺少 files")
    raw_output = str(params.get("output_path") or "").strip()
    if not raw_output:
        raise ValueError("缺少 output_path")
    output = _resolve(workspace, raw_output)
    writer = PdfWriter()
    for raw in files:
        source = _resolve(workspace, str(raw))
        if not source.is_file():
            raise ValueError(f"文件不存在: {source}")
        reader = PdfReader(str(source))
        for page in reader.pages:
            writer.add_page(page)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)
    print(
        json.dumps(
            {
                "success": True,
                "message": "PDF 合并完成",
                "file_name": output.name,
                "filepath": str(output),
            },
            ensure_ascii=False,
        )
    )


def _split(workspace: Path, params: dict) -> None:
    raw = str(params.get("file_path") or "").strip()
    if not raw:
        raise ValueError("缺少 file_path")
    source = _resolve(workspace, raw)
    if not source.is_file():
        raise ValueError(f"文件不存在: {source}")
    reader = PdfReader(str(source))
    total = len(reader.pages)
    raw_dir = str(params.get("output_dir") or "").strip()
    output_dir = _resolve(workspace, raw_dir) if raw_dir else source.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    pages_spec = str(params.get("pages") or "").strip()
    if pages_spec:
        page_numbers = _parse_pages(pages_spec, total)
        writer = PdfWriter()
        for number in page_numbers:
            writer.add_page(reader.pages[number - 1])
        output = output_dir / f"{source.stem}_extract.pdf"
        with output.open("wb") as handle:
            writer.write(handle)
        print(
            json.dumps(
                {
                    "success": True,
                    "message": f"已提取 {len(page_numbers)} 页",
                    "file_name": output.name,
                    "filepath": str(output),
                },
                ensure_ascii=False,
            )
        )
        return

    paths = []
    for index, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)
        output = output_dir / f"{source.stem}_page_{index:03d}.pdf"
        with output.open("wb") as handle:
            writer.write(handle)
        paths.append(str(output))
    print(
        json.dumps(
            {
                "success": True,
                "message": f"已拆分为 {len(paths)} 个文件",
                "content": json.dumps(paths, ensure_ascii=False),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    action = str(params.get("action") or "").strip().lower()
    try:
        if action == "merge":
            _merge(workspace, params)
        elif action == "split":
            _split(workspace, params)
        else:
            print(json.dumps({"success": False, "message": "action 必须是 merge 或 split"}))
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"PDF 处理失败: {exc}"},
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
