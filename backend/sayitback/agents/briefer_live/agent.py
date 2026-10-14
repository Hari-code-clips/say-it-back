"""ADK agent: the Live briefer, run with Runner.run_live (bidirectional streaming).

Its instruction is built on the server from the round's script and the language lock, and it
never contains steps, essentials or ratings. The state it reads has the worker-language script
only: instruction, question texts and closing.
"""

from __future__ import annotations

from collections.abc import Callable

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext

from sayitback import demo, prompts
from sayitback.adk_common import read_input
from sayitback.runtime import Runtime, get_runtime

NAME = "briefer_live"


def instruction(ctx: ReadonlyContext) -> str:
    return prompts.briefer_instruction(read_input(ctx, demo.briefer_input))


def build_agent(
    rt: Runtime | None = None, on_connected: Callable[[], None] | None = None
) -> LlmAgent:
    """`on_connected` fires when the Live session is open (the relay then sends `ready`)."""
    rt = rt or get_runtime()
    return LlmAgent(
        name=NAME,
        description="Reads the approved script aloud in the worker's language, asks the questions.",
        model=rt.live_factory(on_connected),
        instruction=instruction,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


root_agent = build_agent()
