"""Unit tests for utils/llm_client.py.

These mock the Anthropic SDK entirely -- no network calls, no API key
needed. They test the adapter's own logic (structured-output extraction,
the web-search nudge loop, config resolution), not the vendor SDK.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils import llm_client  # noqa: E402


def _tool_use_block(name: str, input_: dict):
    return SimpleNamespace(type="tool_use", name=name, input=input_)


def _text_block(text: str = "thinking..."):
    return SimpleNamespace(type="text", text=text)


def test_load_stage_config_known_stage():
    cfg = llm_client.load_stage_config("analysis")
    assert cfg == {"provider": "anthropic", "model": "claude-sonnet-5"}


def test_load_stage_config_unknown_stage_falls_back_to_default():
    cfg = llm_client.load_stage_config("some_stage_not_in_yaml")
    assert cfg["provider"] and cfg["model"]  # falls back to "default" section


def test_call_llm_extracts_structured_output(monkeypatch):
    fake_message = SimpleNamespace(
        content=[_tool_use_block("structured_output", {"answer": 42})]
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_message
    monkeypatch.setattr(llm_client, "_anthropic_client", lambda: fake_client)

    result = llm_client.call_llm(
        "prompt", {"type": "object"}, provider="anthropic", model="claude-sonnet-5"
    )

    assert result == {"answer": 42}
    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "structured_output"}


def test_call_llm_raises_if_no_tool_call(monkeypatch):
    fake_message = SimpleNamespace(content=[_text_block()])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_message
    monkeypatch.setattr(llm_client, "_anthropic_client", lambda: fake_client)

    with pytest.raises(llm_client.LLMConfigError):
        llm_client.call_llm(
            "prompt", {"type": "object"}, provider="anthropic", model="claude-sonnet-5"
        )


def test_call_llm_with_web_search_nudges_until_submitted(monkeypatch):
    # First turn: model only searches (no structured_output call yet).
    # Second turn: model submits.
    responses = [
        SimpleNamespace(content=[_text_block("searching...")]),
        SimpleNamespace(content=[_tool_use_block("structured_output", {"candidates": []})]),
    ]
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = responses
    monkeypatch.setattr(llm_client, "_anthropic_client", lambda: fake_client)

    result = llm_client.call_llm_with_web_search(
        "prompt", {"type": "object"}, provider="anthropic", model="claude-sonnet-5"
    )

    assert result == {"candidates": []}
    assert fake_client.messages.create.call_count == 2


def test_call_llm_with_web_search_gives_up_after_max_rounds(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = SimpleNamespace(
        content=[_text_block("still searching...")]
    )
    monkeypatch.setattr(llm_client, "_anthropic_client", lambda: fake_client)

    with pytest.raises(llm_client.LLMConfigError):
        llm_client.call_llm_with_web_search(
            "prompt", {"type": "object"}, provider="anthropic", model="claude-sonnet-5"
        )
