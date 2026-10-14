"""ADK agent: read the supervisor's instruction against the SOP and return the critical steps."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext

from sayitback import demo, prompts
from sayitback.adk_common import build_llm_agent, read_input
from sayitback.llm_schemas import ExtractOut
from sayitback.runtime import Runtime, get_runtime

NAME = "extract_steps"
OUTPUT_KEY = "extract_out"


def instruction(ctx: ReadonlyContext) -> str:
    return prompts.extract_instruction(read_input(ctx, demo.extract_input))


def build_agent(rt: Runtime | None = None) -> LlmAgent:
    return build_llm_agent(
        NAME,
        rt or get_runtime(),
        instruction,
        ExtractOut,
        output_key=OUTPUT_KEY,
        description="Extracts atomic critical steps, hazards and essentials; tags SOP-only steps.",
    )


root_agent = build_agent()
