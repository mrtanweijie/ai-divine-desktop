import json
import shutil
import subprocess
import sys


def _read_clipboard() -> str:
    if sys.platform == "darwin":
        completed = subprocess.run(["pbpaste"], capture_output=True, text=True)
        return completed.stdout or ""
    if sys.platform.startswith("win"):
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True,
            text=True,
        )
        return completed.stdout or ""
    for command in (
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
    ):
        if shutil.which(command[0]):
            completed = subprocess.run(
                command, capture_output=True, text=True
            )
            return completed.stdout or ""
    return ""


def _write_clipboard(content: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=content, text=True, check=True)
        return
    if sys.platform.startswith("win"):
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard"],
            input=content,
            text=True,
            check=True,
        )
        return
    for command in (
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ):
        if shutil.which(command[0]):
            subprocess.run(command, input=content, text=True, check=True)
            return
    raise RuntimeError("未找到可用的剪贴板工具")


def main() -> None:
    data = json.load(sys.stdin)
    params = data.get("params") or {}
    action = str(params.get("action") or "read").strip().lower()
    try:
        if action == "write":
            content = str(params.get("content") or "")
            _write_clipboard(content)
            print(
                json.dumps(
                    {
                        "success": True,
                        "message": "已写入剪贴板",
                        "content_len": len(content),
                    },
                    ensure_ascii=False,
                )
            )
            return
        if action == "clear":
            _write_clipboard("")
            print(
                json.dumps(
                    {"success": True, "message": "已清空剪贴板"},
                    ensure_ascii=False,
                )
            )
            return
        content = _read_clipboard()
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"剪贴板操作失败: {exc}"},
                ensure_ascii=False,
            )
        )
        return
    capped = content[:50000]
    print(
        json.dumps(
            {
                "success": True,
                "message": "已读取剪贴板",
                "content": capped,
                "truncated": len(content) > len(capped),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
