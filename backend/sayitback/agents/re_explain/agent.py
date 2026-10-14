"""ADK agent: a short, focused re-explanation of the steps the worker could not yet say."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext

from sayitback import demo, prompts
from sayitback.adk_common import build_llm_agent, read_input
from sayitback.llm_schemas import ReExplainOut
from sayitback.runtime import Runtime, get_runtime

NAME = "re_explain"
OUTPUT_KEY = "re_explain_out"


def instruction(ctx: ReadonlyContext) -> str:
    return prompts.re_explain_instruction(read_input(ctx, demo.re_explain_input))


def build_agent(rt: Runtime | None = None) -> LlmAgent:
    return build_llm_agent(
        NAME,
        rt or get_runtime(),
        instruction,
        ReExplainOut,
        output_key=OUTPUT_KEY,
        description="Writes the supervisor's focused re-explanation of the open steps.",
    )


root_agent = build_agent()
