"""Core subpackage: shared leaves used across all agent subpackages.

Holds the modules with the highest fan-in (schema/context/constants),
LLM providers, model registry, and SSE formatting. Importing from here
keeps ``intent``/``tools``/``state``/``middleware`` acyclic: core never
imports from sibling subpackages.

Note: ``prompts`` is intentionally NOT re-exported here. It is a hub that
legitimately depends on ``intent``/``rag``/``state``/``middleware`` (dynamic
prompt assembly pulls in rule sections and plan progress), so aggregating it
into this ``__init__`` would create a core ↔ sibling cycle. Consumers import
``..core.prompts`` directly.
"""

from __future__ import annotations

from .constants import (
    SYSTEM_PROMPT,
    MAX_TOOL_TURNS,
    _NO_PLAN_TOOLS,
    _READ_ONLY_TOOLS,
)
from .context import AgentRunContext, canonical_path, estimate_tokens
from .llm import (
    MockChatModel,
    _build_llm,
    _resolve_model_entry,
    _resolve_tool_mode,
    generate_session_title,
)
from .local_llm import LocalLLMManager, get_manager, local_model_entry
from .model_registry import detect_hardware, get_recommended_models
from .prompt_sections import (
    _OPTIONS_CARD_RULES,
)
from .schema import (
    _content_text,
    _make_args_model,
    _run_skill_script,
    _skill_args_model,
    _skill_tool_name,
)
from .sse import (
    _interrupt_sse,
    _stream_agent_run,
)

__all__ = [
    "AgentRunContext",
    "LocalLLMManager",
    "MockChatModel",
    "SYSTEM_PROMPT",
    "canonical_path",
    "detect_hardware",
    "estimate_tokens",
    "generate_session_title",
    "get_manager",
    "get_recommended_models",
    "local_model_entry",
]
