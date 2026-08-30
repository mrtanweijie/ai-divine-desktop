"""Scripted chat model for harness smoke tests (zero API cost).

``build_fake_llm`` turns a scenario's ``solution`` ops (config.yaml) into a
sequence of AIMessages that carry real tool_calls. Running the harness with
``--fake`` executes the full production stack — real tools, real approval
bypass, real edit_files, real pytest grading — with a deterministic model, so
the harness itself is regression-tested without spending tokens.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChatModel(BaseChatModel):
    """Replays a fixed list of AIMessages; ignores tools and history."""

    responses: list
    cursor: int = 0

    @property
    def _llm_type(self) -> str:
        return "eval_scripted"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN202
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001, ANN202
        index = min(self.cursor, len(self.responses) - 1)
        self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=self.responses[index])])


def build_fake_llm(ops: list[dict]) -> ScriptedChatModel:
    """One AIMessage per solution op (a tool call), then a final answer."""
    responses: list[AIMessage] = []
    for index, op in enumerate(ops):
        responses.append(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": op["tool"],
                        "args": op.get("args") or {},
                        "id": f"fake_call_{index}",
                        "type": "tool_call",
                    }
                ],
            )
        )
    responses.append(AIMessage(content="已按方案完成全部修改并通过验证。"))
    return ScriptedChatModel(responses=responses)
