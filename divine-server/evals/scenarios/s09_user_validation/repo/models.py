"""用户模型。"""


class User:
    def __init__(self, name: str, email: str) -> None:
        self.name = name
        self.email = email

    def __repr__(self) -> str:  # pragma: no cover
        return f"User({self.name!r}, {self.email!r})"
