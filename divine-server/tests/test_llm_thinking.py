import json

from langchain_core.messages import convert_to_messages

from app.llm.langchain import ChatDeepSeekProvider, thinking_extra_body
from app.llm.legacy import DeepSeekLLM
from app.llm.thinking import normalize_reasoning_effort


def test_thinking_extra_body():
    assert thinking_extra_body(True) == {
        "thinking": {"type": "enabled"}
    }
    assert thinking_extra_body(False) == {
        "thinking": {"type": "disabled"}
    }


def test_chat_deepseek_provider_configures_thinking():
    enabled = ChatDeepSeekProvider(think=True)
    disabled = ChatDeepSeekProvider(think=False)

    assert enabled.llm.extra_body == {"thinking": {"type": "enabled"}}
    assert disabled.llm.extra_body == {"thinking": {"type": "disabled"}}


def test_normalize_reasoning_effort_mapping():
    # Doc mapping: low->low, medium->high, high->high, xhigh->high, max->max
    assert normalize_reasoning_effort("low") == "low"
    assert normalize_reasoning_effort("medium") == "high"
    assert normalize_reasoning_effort("high") == "high"
    assert normalize_reasoning_effort("xhigh") == "high"
    assert normalize_reasoning_effort("max") == "max"
    # Case-insensitive; unknown/missing fall back to the default.
    assert normalize_reasoning_effort("MAX") == "max"
    assert normalize_reasoning_effort("High") == "high"
    assert normalize_reasoning_effort("turbo") == "high"
    assert normalize_reasoning_effort(None) == "high"
    assert normalize_reasoning_effort("") == "high"


def test_chat_deepseek_provider_effort_and_temperature():
    enabled = ChatDeepSeekProvider(think=True, effort="low")
    assert enabled.llm.reasoning_effort == "low"
    # Sampling params are ignored by thinking mode -> not sent.
    assert enabled.llm.temperature is None

    medium = ChatDeepSeekProvider(think=True, effort="medium")
    assert medium.llm.reasoning_effort == "high"

    disabled = ChatDeepSeekProvider(think=False, effort="max")
    assert disabled.llm.reasoning_effort is None
    assert disabled.llm.temperature == 0.7


def test_deepseek_llm_build_payload_thinking_toggle():
    llm = DeepSeekLLM()
    llm.settings = {
        "model": "deepseek-v4-flash",
        "reasoning_effort": "xhigh",
    }
    messages = [{"role": "user", "content": "hi"}]

    on = llm._build_payload(messages, think=True)
    assert on["thinking"] == {"type": "enabled"}
    assert on["reasoning_effort"] == "high"  # xhigh maps to high
    assert "temperature" not in on

    off = llm._build_payload(messages, think=False)
    assert off["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in off
    assert off["temperature"] == 0.7

    with_tools = llm._build_payload(
        messages, tools=[{"type": "function"}], think=True
    )
    assert with_tools["tools"] == [{"type": "function"}]
    assert with_tools["tool_choice"] == "auto"


def test_tool_call_reasoning_content_round_trip():
    """Requests carrying tools must send back reasoning_content with the
    tool-calling assistant message, otherwise DeepSeek returns 400."""
    provider = ChatDeepSeekProvider(think=True, effort="max")
    bound = provider.llm.bind_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "get_date",
                    "description": "Get current date",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
    )
    messages = convert_to_messages(
        [
            {"role": "user", "content": "今天杭州天气如何？"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_date", "arguments": "{}"},
                    }
                ],
                "reasoning_content": "需要先获取日期",
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "2026-04-19"},
        ]
    )
    payload = bound._get_request_payload(messages)
    assistant = payload["messages"][1]
    assert assistant["reasoning_content"] == "需要先获取日期"
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert payload["reasoning_effort"] == "max"
    assert payload["extra_body"] == {"thinking": {"type": "enabled"}}


def test_legacy_payload_passes_reasoning_content_through():
    """Legacy provider sends history dicts as-is; reasoning_content embedded
    by history_for_model must reach the API unchanged."""
    llm = DeepSeekLLM()
    llm.settings = {"model": "deepseek-v4-flash", "reasoning_effort": "high"}
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "思考中",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "get_date", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "2026-04-19"},
    ]
    payload = llm._build_payload(messages, think=True)
    assert payload["messages"][1]["reasoning_content"] == "思考中"
    assert payload["messages"][1]["tool_calls"][0]["id"] == "c1"
    assert payload["thinking"] == {"type": "enabled"}


def test_settings_schema_exposes_reasoning_effort():
    from app.schemas import SettingsUpdate, StreamChatRequest

    request = StreamChatRequest(question="hi", think=True, reasoning_effort="max")
    assert request.reasoning_effort == "max"

    update = SettingsUpdate(reasoning_effort="medium")
    assert update.model_dump(exclude_unset=True) == {"reasoning_effort": "medium"}
