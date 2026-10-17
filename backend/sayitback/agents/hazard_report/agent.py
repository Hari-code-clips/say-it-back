"""ADK agent: a worker's spoken hazard report (API.md v0.4, endpoint 21), audio in the user message.

It transcribes the report verbatim in the worker's own script and translates it into the
supervisor's language. One Flash call; its thinking level is SIB_THINKING_HAZARD_REPORT (low).
If the session state is empty (adk web), it loads the demo's languages (English, Tamil).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext

from sayitback import demo, prompts
from sayitback.adk_common import build_llm_agent, read_input
from sayitback.llm_schemas import HazardOut
from sayitback.runtime import Runtime, get_runtime

NAME = "hazard_report"
OUTPUT_KEY = "hazard_out"


def instruction(ctx: ReadonlyContext) -> str:
    return prompts.hazard_report_instruction(read_input(ctx, demo.hazard_report_input))


def build_agent(rt: Runtime | None = None) -> LlmAgent:
    return build_llm_agent(
        NAME,
        rt or get_runtime(),
        instruction,
        HazardOut,
        output_key=OUTPUT_KEY,
        description="Verbatim transcript and translation of a worker's spoken hazard report.",
    )


root_agent = build_agent()
