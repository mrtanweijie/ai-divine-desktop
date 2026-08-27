"""Shared normalized text-file IO for editing tools.

Editing works in a canonical space (LF line endings, no BOM) so matching and
line numbering are platform-independent; writes restore each file's original
encoding traits exactly. All functions are synchronous — callers in async
contexts should wrap them in ``asyncio.to_thread``.
"""

from __future__ import annotations

from pathlib import Path


class TextFileTraits:
    """Original encoding traits of one file: BOM presence + line-ending style."""

    __slots__ = ("had_bom", "eol")

    def __init__(self, had_bom: bool, eol: str) -> None:
        self.had_bom = had_bom
        self.eol = eol


def read_normalized(target: Path) -> tuple[str, TextFileTraits]:
    """Read a UTF-8 text file as LF/no-BOM, returning its original traits.

    ``newline=""`` disables universal-newline translation so CRLF files keep
    their style on write-back instead of being silently converted to LF.
    """
    with target.open("r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    had_bom = text.startswith("\ufeff")
    if had_bom:
        text = text[1:]
    eol = "crlf" if "\r\n" in text else "lf"
    return text.replace("\r\n", "\n"), TextFileTraits(had_bom, eol)


def write_restored(
    target: Path, text: str, traits: TextFileTraits | None
) -> None:
    """Write LF/no-BOM editing output back with the file's original traits."""
    eol = traits.eol if traits else "lf"
    out = text.replace("\n", "\r\n") if eol == "crlf" else text
    if traits and traits.had_bom:
        out = "\ufeff" + out
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        handle.write(out)
