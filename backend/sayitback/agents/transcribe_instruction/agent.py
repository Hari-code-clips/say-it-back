"""ADK agent: transcribe the supervisor's spoken instruction (audio in the user message)."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext

from sayitback import demo, prompts
from sayitback.adk_common import build_llm_agent, read_input
from sayitback.llm_schemas import SpokenText
from sayitback.runtime import Runtime, get_runtime

NAME = "transcribe_instruction"
OUTPUT_KEY = "transcript_out"


def instruction(ctx: ReadonlyContext) -> str:
    return prompts.transcribe_instruction_text(read_input(ctx, demo.transcribe_instruction_input))


def build_agent(rt: Runtime | None = None) -> LlmAgent:
    return build_llm_agent(
        NAME,
        rt or get_runtime(),
        instruction,
        SpokenText,
        output_key=OUTPUT_KEY,
        description="Verbatim transcript of the supervisor's spoken instruction.",
    )


root_agent = build_agent()
