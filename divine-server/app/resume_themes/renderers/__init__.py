"""Theme renderer registry used by the resume PDF facade."""

from __future__ import annotations

from .finance import _render_finance, _render_linkedin
from .kami import _render_kami, _render_kami_white, _render_kami_original
from .professional import (
    _render_boss_zhipin,
    _render_creative,
    _render_flat_resume,
    _render_minimal,
    _render_professional,
)

_RENDERERS = {
    "professional": _render_professional,
    "creative": _render_creative,
    "minimal": _render_minimal,
    "boss_zhipin": _render_boss_zhipin,
    "finance": _render_finance,
    "linkedin": _render_linkedin,
    "kami": _render_kami,
    "kami_white": _render_kami_white,
}

__all__ = ["_RENDERERS"]
