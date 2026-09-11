"""GraphIR contract package — enums, limits and validation for ``render_graph``.

The interactive-graph pipeline takes a declarative IR from the LLM. This package
is the backend authority for *what a legal IR looks like*:

- :mod:`~app.tools.graph.schema` — closed enums, per-scenario limits, JSON Schema
- :mod:`~app.tools.graph.validator` — the §3 checklist, returning path-addressed
  structured errors that the Agent can act on

Frontend mirror: ``divine-app/src/pages/chat/components/GraphBlock/GraphIR.ts``.
"""

from .schema import (
    GRAPH_KINDS,
    KIND_LABELS,
    NODE_LIMITS,
    json_schema,
    node_limit,
)
from .validator import GraphIrIssue, GraphIrValidation, validate_graph_ir

__all__ = [
    "GRAPH_KINDS",
    "KIND_LABELS",
    "NODE_LIMITS",
    "GraphIrIssue",
    "GraphIrValidation",
    "json_schema",
    "node_limit",
    "validate_graph_ir",
]
