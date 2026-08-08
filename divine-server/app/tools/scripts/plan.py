import json
import sys


def main() -> None:
    data = json.load(sys.stdin)
    params = data.get("params") or {}
    items = [str(item).strip() for item in params.get("items") or []]
    if not items:
        print(json.dumps({"success": False, "message": "计划项不能为空"}))
        return
    print(
        json.dumps(
            {
                "success": True,
                "message": f"计划已创建，共 {len(items)} 项",
                "count": len(items),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
