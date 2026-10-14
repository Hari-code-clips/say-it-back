"""ADK agent: back-translate the worker-language script for the supervisor.

A separate agent from the script writer, and it never sees the steps, so the supervisor reads
what the worker will actually hear and not a restatement of what was meant.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext

from sayitback import demo, prompts
from sayitback.adk_common import build_llm_agent, read_input
from sayitback.llm_schemas import BackOut
from sayitback.runtime import Runtime, get_runtime

NAME = "back_translate"
OUTPUT_KEY = "back_out"


def instruction(ctx: ReadonlyContext) -> str:
    return prompts.back_translate_instruction(read_input(ctx, demo.back_translate_input))


def build_agent(rt: Runtime | None = None) -> LlmAgent:
    return build_llm_agent(
        NAME,
        rt or get_runtime(),
        instruction,
        BackOut,
        output_key=OUTPUT_KEY,
        description="Faithful back-translation of the worker script into the supervisor language.",
    )


root_agent = build_agent()
