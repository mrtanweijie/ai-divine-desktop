"""文本清洗流水线。"""

from normalize import strip_spaces


def clean_line(line: str) -> str:
    """清洗一行文本：去掉首尾空白（包括空格与制表符）并压缩内部连续空格。"""
    line = strip_spaces(line)
    while "  " in line:
        line = line.replace("  ", " ")
    return line


def clean_document(text: str) -> list[str]:
    return [clean_line(line) for line in text.splitlines()]
