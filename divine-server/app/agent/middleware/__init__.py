"""Middleware subpackage: cross-cutting pre-processing for agent runs."""

from __future__ import annotations

from .middleware import TodoSyncMiddleware
from .preprocess import (
    _start_local_model,
    maybe_preprocess,
    maybe_preprocess_attachment,
)
from .project_context import (
    build_project_context,
    clear_project_context_cache,
    _looks_like_project,
)

__all__ = [
    "TodoSyncMiddleware",
    "build_project_context",
    "clear_project_context_cache",
    "maybe_preprocess",
    "maybe_preprocess_attachment",
]
