import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.rag_store import index_workspace  # noqa: E402


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    extra_path = str(params.get("path") or "").strip()
    try:
        result = index_workspace(workspace, extra_path)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"建立索引失败: {exc}"},
                ensure_ascii=False,
            )
        )
        return
    print(
        json.dumps(
            {
                "success": True,
                "message": (
                    f"本地索引完成：{result['files']} 个文件，"
                    f"{result['chunks']} 个分块"
                ),
                "content": json.dumps(result, ensure_ascii=False),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
