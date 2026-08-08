import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.document_reader import read_file_text  # noqa: E402


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
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"success": False, "message": f"读取失败: {exc}"}))
        return

    capped = content[:12000]
    print(
        json.dumps(
            {
                "success": True,
                "message": f"已读取 {path.name}",
                "file_name": path.name,
                "filepath": str(path),
                "content": capped,
                "truncated": len(content) > len(capped),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
