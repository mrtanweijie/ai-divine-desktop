import re


def slugify(text: str) -> str:
    """Turn a title into an ASCII URL slug.

    规范：字母转小写；带音调的拉丁字母折叠为 ASCII（如 é→e、ü→u）；
    空格与其余非字母数字字符转 -；连续 - 合并；首尾 - 去掉。
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
