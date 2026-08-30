"""按 URL + 查询参数缓存的简易抓取缓存。"""


class FetchCache:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    @staticmethod
    def build_key(url: str, params: dict | None) -> str:
        if not params:
            return url
        return url

    def get(self, url: str, params: dict | None = None) -> str | None:
        return self._store.get(self.build_key(url, params))

    def put(self, url: str, body: str, params: dict | None = None) -> None:
        self._store[self.build_key(url, params)] = body
