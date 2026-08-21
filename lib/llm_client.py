"""Provider-independent LLM adapter.

Pipeline scripts (judge.py / analyze.py / fetch_candidates.py) only ever
import from this module. Nobody outside this file imports a vendor SDK
directly, and nobody outside this file knows what "provider" a given stage
is configured to use.

Two entry points:

    call_llm(prompt, schema, ...)
        One prompt -> one structured JSON output. No tools, no network
        access on the model's side. This is the default shape for any
        stage that only needs to reason over data we already gathered
        (headline_judge, analysis).

    call_llm_with_web_search(prompt, schema, ...)
        Same contract, but the model is additionally given a *hosted*
        (server-side) web-search tool it can call on its own before
        producing the final structured output. This is an intentional,
        narrow exception to "LLM only does one prompt+schema completion"
        for the 02_collect_headlines/fetch_candidates.py stage only -- see
        AGENTS.md section 4a for why. It still does not depend on any
        coding-agent CLI's tool ecosystem (no Claude Code WebSearch/Bash);
        the search tool is a feature of the model provider's own API.

Provider/model selection lives in config/llm.yaml, keyed by stage name.
Add a new provider by adding one `_call_<provider>` / one
`_call_<provider>_with_web_search` function below and registering it in
the dispatch tables at the bottom of the file -- nothing else in the repo
needs to change.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LLM_CONFIG_PATH = REPO_ROOT / "config" / "llm.yaml"

_STRUCTURED_OUTPUT_TOOL_NAME = "structured_output"
_MAX_SEARCH_ROUNDS = 4  # safety cap on tool-use turns for call_llm_with_web_search


class LLMConfigError(RuntimeError):
    pass


def load_stage_config(stage: str) -> dict:
    """Read config/llm.yaml and return {"provider": ..., "model": ...} for `stage`.

    Falls back to the "default" section if `stage` has no entry of its own.
    """
    with open(LLM_CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    section = cfg.get(stage) or cfg.get("default")
    if not section:
        raise LLMConfigError(
            f"No '{stage}' or 'default' section in {LLM_CONFIG_PATH}"
        )
    provider = section.get("provider")
    model = section.get("model")
    if not provider or not model:
        raise LLMConfigError(f"'{stage}' section in {LLM_CONFIG_PATH} needs provider+model")
    return {"provider": provider, "model": model}


def _resolve(provider: str | None, model: str | None, stage: str | None) -> tuple[str, str]:
    if provider and model:
        return provider, model
    if stage:
        cfg = load_stage_config(stage)
        return provider or cfg["provider"], model or cfg["model"]
    provider = provider or os.environ.get("DEFAULT_LLM_PROVIDER")
    model = model or os.environ.get("DEFAULT_LLM_MODEL")
    if not provider or not model:
        raise LLMConfigError(
            "provider/model not given and no stage/env default available"
        )
    return provider, model


def call_llm(
    prompt: str,
    schema: dict,
    *,
    provider: str | None = None,
    model: str | None = None,
    system: str | None = None,
    stage: str | None = None,
) -> dict:
    """Prompt + JSON schema -> dict matching that schema. No tools."""
    provider, model = _resolve(provider, model, stage)
    try:
        fn = _COMPLETION_BACKENDS[provider]
    except KeyError:
        raise LLMConfigError(f"unknown provider '{provider}'") from None
    return fn(prompt=prompt, schema=schema, model=model, system=system)


def call_llm_with_web_search(
    prompt: str,
    schema: dict,
    *,
    provider: str | None = None,
    model: str | None = None,
    system: str | None = None,
    stage: str | None = None,
    max_uses: int = 5,
) -> dict:
    """Prompt + hosted web-search tool + JSON schema -> dict.

    The model may issue any number of server-side web searches (capped at
    `max_uses`) before returning a result matching `schema`. See module
    docstring for why this exists as a deliberate, narrow exception.
    """
    provider, model = _resolve(provider, model, stage)
    try:
        fn = _WEB_SEARCH_BACKENDS[provider]
    except KeyError:
        raise LLMConfigError(
            f"provider '{provider}' has no web-search-enabled backend implemented"
        ) from None
    return fn(prompt=prompt, schema=schema, model=model, system=system, max_uses=max_uses)


# --------------------------------------------------------------------------
# Anthropic backend
# --------------------------------------------------------------------------

def _anthropic_client():
    import anthropic  # local import: keep vendor SDKs optional at module load

    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


def _structured_output_tool(schema: dict) -> dict:
    return {
        "name": _STRUCTURED_OUTPUT_TOOL_NAME,
        "description": "Return the final answer. Always call this exactly once, when you are done.",
        "input_schema": schema,
    }


def _extract_tool_input(message, tool_name: str) -> dict | None:
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input
    return None


def _call_anthropic(*, prompt: str, schema: dict, model: str, system: str | None) -> dict:
    client = _anthropic_client()
    tool = _structured_output_tool(schema)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system or "",
        messages=[{"role": "user", "content": prompt}],
        tools=[tool],
        tool_choice={"type": "tool", "name": _STRUCTURED_OUTPUT_TOOL_NAME},
    )
    result = _extract_tool_input(message, _STRUCTURED_OUTPUT_TOOL_NAME)
    if result is None:
        raise LLMConfigError("anthropic response did not include structured_output tool call")
    return result


def _call_anthropic_with_web_search(
    *, prompt: str, schema: dict, model: str, system: str | None, max_uses: int
) -> dict:
    client = _anthropic_client()
    tools = [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses},
        _structured_output_tool(schema),
    ]
    messages: list[dict] = [{"role": "user", "content": prompt}]

    for round_num in range(_MAX_SEARCH_ROUNDS):
        force_submit = round_num == _MAX_SEARCH_ROUNDS - 1
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system or "",
            messages=messages,
            tools=tools,
            tool_choice=(
                {"type": "tool", "name": _STRUCTURED_OUTPUT_TOOL_NAME}
                if force_submit
                else {"type": "auto"}
            ),
        )
        result = _extract_tool_input(message, _STRUCTURED_OUTPUT_TOOL_NAME)
        if result is not None:
            return result

        # Model did a round of (server-executed) web searches but hasn't
        # submitted yet. Anthropic already resolved the web_search tool
        # calls server-side and included the results in `message.content`;
        # we just need to carry the turn forward and nudge it to finish.
        messages.append({"role": "assistant", "content": message.content})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Continue. When you have enough information, call the "
                    f"'{_STRUCTURED_OUTPUT_TOOL_NAME}' tool with your final answer."
                ),
            }
        )

    raise LLMConfigError(
        f"anthropic web-search loop exceeded {_MAX_SEARCH_ROUNDS} rounds without a result"
    )


# --------------------------------------------------------------------------
# OpenAI-compatible backend (covers OpenAI itself and any OpenAI-compatible
# gateway, e.g. a self-hosted or third-party endpoint, via OPENAI_BASE_URL).
# --------------------------------------------------------------------------

def _openai_client():
    from openai import OpenAI  # local import, optional dependency

    base_url = os.environ.get("OPENAI_BASE_URL")  # None => official OpenAI endpoint
    return OpenAI(base_url=base_url) if base_url else OpenAI()


def _call_openai(*, prompt: str, schema: dict, model: str, system: str | None) -> dict:
    client = _openai_client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "structured_output", "schema": schema, "strict": True},
        },
    )
    return json.loads(response.choices[0].message.content)


def _call_openai_with_web_search(
    *, prompt: str, schema: dict, model: str, system: str | None, max_uses: int
) -> dict:
    raise LLMConfigError(
        "openai web-search backend not implemented yet -- "
        "wire up the Responses API hosted 'web_search' tool here when needed"
    )


# --------------------------------------------------------------------------
# Backend registries -- add a provider by adding one line to each dict.
# --------------------------------------------------------------------------

_COMPLETION_BACKENDS: dict[str, Any] = {
    "anthropic": _call_anthropic,
    "openai": _call_openai,
}

_WEB_SEARCH_BACKENDS: dict[str, Any] = {
    "anthropic": _call_anthropic_with_web_search,
    "openai": _call_openai_with_web_search,
}
