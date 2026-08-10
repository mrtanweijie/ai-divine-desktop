import json
import sys
from pathlib import Path

from PIL import Image


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    raw = str(params.get("file_path") or "").strip()
    if not raw:
        print(json.dumps({"success": False, "message": "缺少 file_path"}))
        return
    source = Path(raw)
    if not source.is_absolute():
        source = workspace / source
    source = source.resolve()
    if not source.is_file():
        print(json.dumps({"success": False, "message": f"文件不存在: {source}"}))
        return
    if source.stat().st_size > 100 * 1024 * 1024:
        print(json.dumps({"success": False, "message": "图片超过 100MB"}))
        return

    width = params.get("width")
    height = params.get("height")
    try:
        width = int(width) if width is not None else None
        height = int(height) if height is not None else None
    except (TypeError, ValueError):
        print(json.dumps({"success": False, "message": "width/height 必须是整数"}))
        return
    if not width and not height:
        print(json.dumps({"success": False, "message": "请提供 width 或 height"}))
        return
    if (width is not None and width <= 0) or (
        height is not None and height <= 0
    ):
        print(json.dumps({"success": False, "message": "width/height 必须大于 0"}))
        return

    raw_output = str(params.get("output_path") or "").strip()
    if raw_output:
        output = Path(raw_output)
        if not output.is_absolute():
            output = workspace / output
        output = output.resolve()
    else:
        output_root = Path(data.get("output_dir") or workspace).resolve()
        output = output_root / "images" / f"{source.stem}_resized{source.suffix}"

    try:
        image = Image.open(source)
        if width and height:
            image = image.resize((width, height), Image.LANCZOS)
        elif width:
            new_height = max(1, round(image.height * width / image.width))
            image = image.resize((width, new_height), Image.LANCZOS)
        else:
            new_width = max(1, round(image.width * height / image.height))
            image = image.resize((new_width, height), Image.LANCZOS)
        quality = int(params.get("quality") or 85)
        save_kwargs = {}
        if output.suffix.lower() in (".jpg", ".jpeg", ".webp"):
            save_kwargs["quality"] = max(1, min(100, quality))
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, **save_kwargs)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"图片处理失败: {exc}"},
                ensure_ascii=False,
            )
        )
        return

    print(
        json.dumps(
            {
                "success": True,
                "message": "图片缩放完成",
                "file_name": output.name,
                "filepath": str(output),
                "width": image.width,
                "height": image.height,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
