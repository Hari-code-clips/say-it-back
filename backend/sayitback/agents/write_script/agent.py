"""ADK agent: write the worker-language instruction and 2-3 open questions for the steps."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext

from sayitback import demo, prompts
from sayitback.adk_common import build_llm_agent, read_input
from sayitback.llm_schemas import ScriptOut
from sayitback.runtime import Runtime, get_runtime

NAME = "write_script"
OUTPUT_KEY = "script_out"


def instruction(ctx: ReadonlyContext) -> str:
    return prompts.script_instruction(read_input(ctx, demo.script_input))


def build_agent(rt: Runtime | None = None) -> LlmAgent:
    return build_llm_agent(
        NAME,
        rt or get_runtime(),
        instruction,
        ScriptOut,
        output_key=OUTPUT_KEY,
        description="Writes short spoken sentences, a step map and questions (worker language).",
    )


root_agent = build_agent()
