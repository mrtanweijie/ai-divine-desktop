def parse_duration(text: str) -> int:
    """Parse ``2h``/``12m``/``45s`` style durations into seconds.

    Raises ValueError for anything that is not a valid duration string.
    """
    text = text.strip().lower()
    if text.endswith("h"):
        return int(text[:-1]) * 3600
    if text.endswith("m"):
        return int(text[:-1]) * 60
    if text.endswith("s"):
        return int(text[:-1])
    raise ValueError(f"invalid duration: {text!r}")
