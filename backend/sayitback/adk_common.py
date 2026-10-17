"""Shared helpers for the ADK agent modules in sayitback/agents/*.

Every instruction is a callable (InstructionProvider) that reads the phase input from session
state, so JSON braces in prompts are never template-substituted. Output schemas give typed
results. Gemini 3.x: no temperature, top_p or top_k; effort is set with thinking_level. Every Flash
call also has an output ceiling, `max_output_tokens` (SIB_MAX_OUTPUT_TOKENS), which thinking tokens
count toward: a reply that hits it is cut off, and adk_run.run_phase turns that into a 502. Each
attempt of a Flash call is cut off after SIB_CALL_TIMEOUT_S and retried (backends.retry_options).
A reply the model's safety filter blocked (the prompt itself, or a candidate with no content) is
asked for again (backends.RefusalRetry); one still blocked on the last attempt is recorded in state
as `refused:<agent>`, so the check can tell it from silence (v0.5.1).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.genai import types
from pydantic import BaseModel

from sayitback.backends import call_http_options, thinking_config
from sayitback.refusal import refusal_reason
from sayitback.runtime import Runtime

log = logging.getLogger("sayitback.run")
INPUT_KEY = "input"  # the phase input, written by the pipeline when the session is created
REFUSED_PREFIX = "refused:"  # + an agent name: the block reason of that agent's reply


def read_input(ctx: ReadonlyContext, demo: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """The phase input from session state, or the catalog demo when state is empty (adk web)."""
    value = ctx.state.get(INPUT_KEY)
    return dict(value) if value else demo()


def record_refusal(*, callback_context: Any, llm_response: Any) -> None:
    """after_model_callback for every Flash agent: note a filtered reply in state, by agent. The
    log names the agent and the reason, never what was sent."""
    reason = refusal_reason(llm_response)
    if reason:
        agent = callback_context.agent_name
        log.warning("agent %s: the reply was blocked by the model's filter (%s)", agent, reason)
        callback_context.state[REFUSED_PREFIX + agent] = reason
    return None


def refused_by(state: Mapping[str, Any], agent: str) -> str | None:
    """The block reason of `agent`'s reply in this session, if the model's filter refused it."""
    value = state.get(REFUSED_PREFIX + agent)
    return str(value) if value else None


def any_refusal(state: Mapping[str, Any]) -> bool:
    return any(str(k).startswith(REFUSED_PREFIX) and v for k, v in state.items())


def build_llm_agent(
    name: str,
    rt: Runtime,
    instruction: Callable[[ReadonlyContext], str],
    schema: type[BaseModel],
    *,
    output_key: str,
    description: str,
    include_contents: str = "default",
    before_model_callback: Any = None,
    model: Any = None,
) -> LlmAgent:
    """One Flash agent: callable instruction, output schema, thinking_level and output ceiling from
    settings.

    Transfers are disabled so ADK's single flow runs and the request carries no transfer tool.
    `model` replaces the Flash model (judge B runs on SIB_JUDGE_B_MODEL); thinking_level still
    applies, so it must be a Gemini 3.x model.
    """
    return LlmAgent(
        name=name,
        description=description,
        model=model or rt.flash,
        instruction=instruction,
        output_schema=schema,
        output_key=output_key,
        include_contents=include_contents,  # type: ignore[arg-type]
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(
            thinking_config=thinking_config(rt.settings.thinking[name]),
            max_output_tokens=rt.settings.max_output_tokens,
            http_options=call_http_options(rt.settings),
        ),
        before_model_callback=before_model_callback,
        after_model_callback=record_refusal,
    )
