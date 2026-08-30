from store import fetch_data


def render_logs() -> str:
    rows = fetch_data("logs")
    return "\n".join(f"{r['id']}: {r['msg']}" for r in rows)
