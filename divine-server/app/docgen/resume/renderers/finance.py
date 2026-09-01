"""Finance and LinkedIn renderers, both built on the shared flat layout."""

from __future__ import annotations

from ..models import ResumeData
from .professional import _render_flat_resume

def _render_finance(resume: ResumeData) -> str:
    return _render_flat_resume(resume, style="finance")

def _render_linkedin(resume: ResumeData) -> str:
    return _render_flat_resume(resume, style="linkedin")
