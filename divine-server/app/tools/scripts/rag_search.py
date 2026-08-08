import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.rag_store import index_workspace, search_workspace  # noqa: E402


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    query = str(params.get("query") or "").strip()
    if not query:
        print(json.dumps({"success": False, "message": "缺少 query"}))
        return
    try:
        top_k = int(params.get("top_k") or 5)
    except (TypeError, ValueError):
        top_k = 5
    top_k = max(1, min(10, top_k))
    try:
        results = search_workspace(workspace, query, top_k)
        if not results:
            index_workspace(workspace)
            results = search_workspace(workspace, query, top_k)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"本地检索失败: {exc}"},
                ensure_ascii=False,
            )
        )
        return
    if not results:
        print(
            json.dumps(
                {"success": True, "message": "没有找到相关内容"},
                ensure_ascii=False,
            )
        )
        return
    print(
        json.dumps(
            {
                "success": True,
                "message": f"找到 {len(results)} 条相关内容",
                "content": json.dumps(results, ensure_ascii=False),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
