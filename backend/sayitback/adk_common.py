"""Shared helpers for the ADK agent modules in sayitback/agents/*.

Every instruction is a callable (InstructionProvider) that reads the phase input from session
state, so JSON braces in prompts are never template-substituted. Output schemas give typed
results. Gemini 3.x: no temperature, top_p or top_k; effort is set with thinking_level. Every Flash
call also has an output ceiling, `max_output_tokens` (SIB_MAX_OUTPUT_TOKENS), which thinking tokens
count toward: a reply that hits it is cut off, and adk_run.run_phase turns that into a 502.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.genai import types
from pydantic import BaseModel

from sayitback.backends import thinking_config
from sayitback.runtime import Runtime

INPUT_KEY = "input"  # the phase input, written by the pipeline when the session is created


def read_input(ctx: ReadonlyContext, demo: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """The phase input from session state, or the catalog demo when state is empty (adk web)."""
    value = ctx.state.get(INPUT_KEY)
    return dict(value) if value else demo()


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
) -> LlmAgent:
    """One Flash agent: callable instruction, output schema, thinking_level and output ceiling from
    settings.

    Transfers are disabled so ADK's single flow runs and the request carries no transfer tool.
    """
    return LlmAgent(
        name=name,
        description=description,
        model=rt.flash,
        instruction=instruction,
        output_schema=schema,
        output_key=output_key,
        include_contents=include_contents,  # type: ignore[arg-type]
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(
            thinking_config=thinking_config(rt.settings.thinking[name]),
            max_output_tokens=rt.settings.max_output_tokens,
        ),
        before_model_callback=before_model_callback,
    )
