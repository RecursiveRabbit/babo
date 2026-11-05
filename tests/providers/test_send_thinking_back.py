"""Earlier turns' thinking sent back (or not), as each provider needs: Moonshot (Kimi) first.

What Moonshot's own client (kosong's Kimi provider) does: every assistant message carries its thinking back as
``reasoning_content`` (empty when a turn had none); preserved thinking (``thinking.keep: "all"``) only on request,
and never without the ``thinking.type`` it goes with.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from babo.config.schema import ModelPresetConfig
from babo.providers.openai_compat_provider import OpenAICompatProvider
from babo.providers.registry import find_by_name

HISTORY: list[dict[str, Any]] = [
    {"role": "user", "content": "Is the garden watered?"},
    {"role": "assistant", "content": None, "reasoning_content": "Check the log.",
     "tool_calls": [{"id": "functions.read:0", "type": "function", "function": {"name": "read", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "functions.read:0", "content": "watered at 07:00"},
    {"role": "assistant", "content": "Yes, at seven."},
    {"role": "user", "content": "And tomorrow?"},
]


def _kwargs(provider: str, model: str, send: str = "auto", effort: str | None = None) -> dict[str, Any]:
    with patch("babo.providers.openai_compat_provider.AsyncOpenAI"):
        p = OpenAICompatProvider(api_key="k", default_model=model, spec=find_by_name(provider))
    p.send_thinking_back = send
    return p._build_kwargs(messages=[dict(m) for m in HISTORY], tools=None, model=model, max_tokens=1024,
                           temperature=0.7, reasoning_effort=effort, tool_choice=None)


def _assistants(kw: dict[str, Any]) -> list[dict[str, Any]]:
    return [m for m in kw["messages"] if m["role"] == "assistant"]


def test_moonshot_gets_thinking_back_on_every_assistant_turn_by_default() -> None:
    kw = _kwargs("moonshot", "kimi-k2.6")
    assert [m.get("reasoning_content") for m in _assistants(kw)] == ["Check the log.", ""]
    assert "keep" not in kw.get("extra_body", {}).get("thinking", {})  # preserved thinking: only on request


def test_on_also_asks_moonshot_to_preserve_thinking_across_turns() -> None:
    kw = _kwargs("moonshot", "kimi-k2.6", send="on")
    assert kw["extra_body"]["thinking"] == {"type": "enabled", "keep": "all"}
    assert "reasoning_effort" not in kw  # Moonshot rejects both together


def test_on_never_turns_thinking_back_on_when_the_preset_turned_it_off() -> None:
    kw = _kwargs("moonshot", "kimi-k2.6", send="on", effort="none")
    assert kw["extra_body"]["thinking"] == {"type": "disabled"}
    assert all("reasoning_content" not in m or m["reasoning_content"] == "Check the log." for m in _assistants(kw))


def test_off_keeps_thinking_out_of_the_conversation() -> None:
    kw = _kwargs("moonshot", "kimi-k2.6", send="off")
    assert all("reasoning_content" not in m for m in _assistants(kw))


@pytest.mark.parametrize("model", ["kimi-k3", "kimi-k2.7-code", "kimi-k2-turbo-preview"])
def test_preserved_thinking_is_asked_for_only_on_models_that_take_it(model: str) -> None:
    kw = _kwargs("moonshot", model, send="on")
    assert "keep" not in kw.get("extra_body", {}).get("thinking", {})


def test_a_provider_that_doesnt_need_it_is_left_alone_unless_asked() -> None:
    plain = _kwargs("openai", "gpt-4o")
    assert [m.get("reasoning_content") for m in _assistants(plain)] == ["Check the log.", None]
    asked = _kwargs("openai", "gpt-4o", send="on")
    assert [m.get("reasoning_content") for m in _assistants(asked)] == ["Check the log.", ""]


def test_a_preset_says_it_and_the_provider_made_from_it_follows() -> None:
    assert ModelPresetConfig(model="kimi-k2.6").send_thinking_back == "auto"
    assert ModelPresetConfig.model_validate({"model": "kimi-k2.6", "sendThinkingBack": "on"}).send_thinking_back == "on"
    with pytest.raises(ValueError):
        ModelPresetConfig.model_validate({"model": "x", "sendThinkingBack": "sometimes"})


@pytest.mark.parametrize(("model", "effort", "expected"), [
    ("kimi-k2.6", None, 16000), ("kimi-k2.7-code", None, 16000), ("kimi-k3.1-pro", "high", 16000),
    ("kimi-k2.6", "none", 1024),  # thinking off: the preset's own limit
    ("kimi-k2-turbo-preview", None, 1024),  # not a thinking model
])
def test_moonshot_thinking_models_get_room_for_thinking_and_answer(model: str, effort: str | None, expected: int) -> None:
    kw = _kwargs("moonshot", model, effort=effort)
    assert (kw.get("max_completion_tokens") or kw.get("max_tokens")) == expected
