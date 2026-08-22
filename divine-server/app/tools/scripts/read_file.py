import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.document_reader import read_file_text  # noqa: E402


def parse_line_range(params: dict) -> tuple[int, int | None]:
    start_line = params.get("start_line")
    end_line = params.get("end_line")
    try:
        start = 1 if start_line is None else int(start_line)
    except (TypeError, ValueError):
        raise ValueError("start_line 必须是整数")
    if start < 1:
        raise ValueError("start_line 必须大于等于 1")

    end = None
    if end_line is not None:
        try:
            end = int(end_line)
        except (TypeError, ValueError):
            raise ValueError("end_line 必须是整数")
        if end < start:
            raise ValueError("end_line 必须大于等于 start_line")
    return start, end


def slice_lines(
    content: str, start: int, end: int | None
) -> tuple[str, int, int]:
    lines = content.splitlines()
    total = len(lines)
    if total > 0 and start > total:
        raise ValueError(f"start_line={start} 超出文件总行数 {total}")
    stop = total if end is None else min(end, total)
    selected = lines[start - 1 : stop]
    return "\n".join(selected), total, stop


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    raw = params.get("file_path") or params.get("path") or ""
    path = Path(raw)
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()

    if path.is_dir():
        print(
            json.dumps(
                {
                    "success": False,
                    "message": f"路径是目录，不是文件: {path}",
                },
                ensure_ascii=False,
            )
        )
        return

    if not path.is_file():
        print(json.dumps({"success": False, "message": f"文件不存在: {path}"}))
        return

    try:
        content = read_file_text(path)
        start, end = parse_line_range(params)
        selected, total_lines, line_end = slice_lines(content, start, end)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"success": False, "message": f"读取失败: {exc}"}))
        return

    capped = selected[:12000]
    has_range = (
        params.get("start_line") is not None
        or params.get("end_line") is not None
    )
    display_start = start if total_lines > 0 else 0
    message = f"已读取 {path.name}"
    if has_range:
        message += f" 第 {display_start}-{line_end} 行（共 {total_lines} 行）"
    truncated = len(selected) > len(capped)
    if truncated:
        # Tell the model how to continue reading instead of dumping more.
        next_start = display_start + len(capped.splitlines())
        if next_start <= total_lines:
            capped += (
                f"\n...(内容已截断，当前显示到第 {min(line_end, display_start + len(capped.splitlines()))} 行，"
                f"共 {total_lines} 行；继续读取请用 start_line={next_start}/end_line 指定行段)"
            )
    print(
        json.dumps(
            {
                "success": True,
                "message": message,
                "file_name": path.name,
                "filepath": str(path),
                "content": capped,
                "truncated": truncated,
                "data": {
                    "total_lines": total_lines,
                    "line_start": start,
                    "line_end": line_end,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
