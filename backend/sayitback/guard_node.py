"""The guard node: a Workflow `FunctionNode` with no model.

It reads the transcriber and judge outputs from session state, applies the pure rules in
guards.py, and writes the final ratings to state. It shows up in traces and in the dev UI graph
like the model nodes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from google.adk.agents.context import Context
from google.adk.events import Event
from google.adk.workflow import FunctionNode
from google.genai import types

from sayitback import catalog, demo
from sayitback.adk_common import INPUT_KEY
from sayitback.check_state import (
    FINAL_KEY,
    JUDGE_A_KEY,
    JUDGE_B_KEY,
    TRANSCRIBE_KEY,
    CheckInput,
    transcripts_from,
)
from sayitback.guards import GuardConfig, GuardResult, run_guards

NAME = "guard"


def guard_state(state: Mapping[str, Any], cfg: GuardConfig) -> GuardResult:
    """Apply guard rules 1-7 to what the earlier nodes left in `state`."""
    inp = CheckInput(state.get(INPUT_KEY) or demo.check_input())
    transcripts = transcripts_from(state.get(TRANSCRIBE_KEY), inp.ids, inp.clip_ids)
    return run_guards(
        steps=inp.steps,
        questions=inp.questions,
        transcripts=transcripts,
        raw_a=state.get(JUDGE_A_KEY),
        raw_b=state.get(JUDGE_B_KEY),
        stats=inp.stats,
        worker_ranges=catalog.unicode_ranges(inp.worker_lang),
        cfg=cfg,
        script=inp.script,
    )


def summary_line(result: GuardResult) -> str:
    """The guard's visible message: verdicts and flags only, never a transcript."""
    parts = [
        f"{r.step_id}: {r.verdict}" + (f" ({', '.join(r.flags)})" if r.flags else "")
        for r in result.ratings
    ]
    return f"Guard rules applied. {'; '.join(parts)}. Next: {result.next_action}."


def guard_event(state: Mapping[str, Any], cfg: GuardConfig) -> Event:
    """The node's one event: the summary line, and the final ratings as a state delta."""
    result = guard_state(state, cfg)
    return Event(
        content=types.Content(role="model", parts=[types.Part(text=summary_line(result))]),
        state={FINAL_KEY: result.model_dump(mode="json")},
    )


def guard_node(cfg: GuardConfig) -> FunctionNode:
    """The guard as a graph node. It ignores its input: the judges' verdicts are in state."""

    def guard(ctx: Context) -> Event:
        """Applies guard rules 1-7 in code and writes the final ratings."""
        return guard_event(ctx.session.state, cfg)

    return FunctionNode(func=guard, name=NAME)
