"""ADK agent: the check workflow, an ADK 2.x `Workflow` graph.

    START -> blind_transcriber -> (judge_a, judge_b) -> join_judges -> guard

- blind_transcriber: LlmAgent, audio in, steps withheld.
- judge_a: LlmAgent on the audio plus the blind transcript. judge_b: the transcript only,
  `include_contents="none"` with media stripped, on a second model (SIB_JUDGE_B_MODEL). They run
  in parallel: a tuple in the chain fans out.
- join_judges: a JoinNode, it waits for both judges.
- guard: a FunctionNode, no model: guards.py rules 1-7.

With SIB_JUDGE_PASSES=1 only judge A runs: START -> blind_transcriber -> judge_a -> guard.
If the session state is empty (adk web), every node loads the catalog's lead demo task
(`lifting-zone`, demo script `sg-lead`; demo.py).
"""

from __future__ import annotations

from typing import Any

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.workflow import START, JoinNode, Workflow

from sayitback import catalog, demo, prompts
from sayitback.adk_common import build_llm_agent, read_input, refused_by
from sayitback.check_state import (
    JUDGE_A,
    JUDGE_A_KEY,
    JUDGE_B,
    JUDGE_B_KEY,
    TRANSCRIBE_KEY,
    TRANSCRIBER,
    question_ids,
    script_view,
    transcripts_from,
)
from sayitback.guard_node import guard_node
from sayitback.guards import GuardConfig
from sayitback.llm_schemas import JudgeOut, TranscribeOut
from sayitback.runtime import Runtime, get_runtime

NAME = "check_answer"
JOIN = "join_judges"


def transcriber_instruction(ctx: ReadonlyContext) -> str:
    """Blind: the worker language, the supervisor language and the clip ids. No steps."""
    inp = read_input(ctx, demo.check_input)
    return prompts.transcriber_instruction(
        {
            "worker_lang_name": inp["worker_lang_name"],
            "supervisor_lang_name": inp["supervisor_lang_name"],
            "clip_ids": inp.get("clip_ids") or question_ids(inp),
            "lang_codes": inp.get("lang_codes") or list(catalog.lang_codes()),
        }
    )


def judge_provider(*, with_audio: bool):
    """An InstructionProvider for judge A (with_audio) or judge B (transcript only)."""

    def instruction(ctx: ReadonlyContext) -> str:
        inp = read_input(ctx, demo.check_input)
        transcripts = transcripts_from(
            ctx.state.get(TRANSCRIBE_KEY),
            question_ids(inp),
            inp.get("clip_ids"),
            refused=bool(refused_by(ctx.state, TRANSCRIBER)),
        )
        return prompts.judge_instruction(
            {
                **inp,
                "script": script_view(inp.get("script")),
                "transcripts": [t.model_dump(mode="json") for t in transcripts],
                "with_audio": with_audio,
            }
        )

    return instruction


def strip_media(*, callback_context: Any, llm_request: Any) -> None:
    """Belt and braces for judge B: no audio or file part may reach it, whatever ADK includes."""
    for content in llm_request.contents or []:
        content.parts = [p for p in (content.parts or []) if not (p.inline_data or p.file_data)]
    return None


def guard_config(rt: Runtime, passes: int) -> GuardConfig:
    s = rt.settings
    return GuardConfig(
        min_confidence=s.covered_min_confidence,
        min_clip_seconds=s.min_clip_seconds,
        silence_rms=s.silence_rms,
        passes=passes,
    )


def build_agent(rt: Runtime | None = None, *, passes: int | None = None) -> Workflow:
    """The check graph for `passes` judges (default: SIB_JUDGE_PASSES). A fresh one per run."""
    rt = rt or get_runtime()
    n_passes = passes or rt.settings.judge_passes
    transcriber = build_llm_agent(
        TRANSCRIBER,
        rt,
        transcriber_instruction,
        TranscribeOut,
        output_key=TRANSCRIBE_KEY,
        description="Verbatim transcripts of each clip with the steps withheld.",
        include_contents="none",  # the node input already is the user's clips: one copy, not two
    )
    judge_a = build_llm_agent(
        JUDGE_A,
        rt,
        judge_provider(with_audio=True),
        JudgeOut,
        output_key=JUDGE_A_KEY,
        description="Judges each step on the audio plus the blind transcript.",
    )  # default contents: the user's clips stay in its history, next to the transcript
    guard = guard_node(guard_config(rt, n_passes))
    if n_passes < 2:
        chain = (START, transcriber, judge_a, guard)
    else:
        judge_b = build_llm_agent(
            JUDGE_B,
            rt,
            judge_provider(with_audio=False),
            JudgeOut,
            output_key=JUDGE_B_KEY,
            description="Judges each step on the blind transcript only.",
            include_contents="none",
            before_model_callback=strip_media,
            model=rt.judge_b,
        )
        chain = (START, transcriber, (judge_a, judge_b), JoinNode(name=JOIN), guard)
    return Workflow(
        name=NAME,
        description="Blind transcriber, two judges in parallel, then the guard.",
        edges=[chain],
    )


root_agent = build_agent()
