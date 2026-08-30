from store import fetch_data


def get_users() -> list[dict]:
    return fetch_data("users")
