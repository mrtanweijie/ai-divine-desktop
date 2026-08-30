from store import fetch_data


class TableCache:
    def __init__(self) -> None:
        self._cache: dict[str, list[dict]] = {}

    def rows(self, table: str) -> list[dict]:
        if table not in self._cache:
            self._cache[table] = fetch_data(table)
        return self._cache[table]
