"""Shared pieces of the check workflow tests: the Tamil answer, a scenario, a `run_check` call, and
the captured model requests told apart by the node that sent them."""

from __future__ import annotations

from google.genai import types

from sayitback import catalog, prompts
from sayitback.llm_schemas import TranscribeOut
from sayitback.models import Question, Step
from sayitback.pipeline import run_check
from tests.fakes import Scenario, rating, tone_wav, transcript

ANSWER = "நான் அதை ஆஃப் பண்ணிட்டு திறப்பேன்."
STEPS = [Step.model_validate(s) for s in catalog.reference_steps("panel-isolation")]
QUESTIONS = [Question(id="q1", text="q?", step_ids=["s1", "s2", "s3"])]


def scenario() -> Scenario:
    """Round 1 of the sg-lead demo: s1 covered, s2 and s3 missed."""
    return Scenario(
        transcripts=[transcript("q1", ANSWER)],
        judge_a=[
            rating("s1", "covered", "ஆஃப் பண்ணிட்டு"),
            rating("s2", "missed"),
            rating("s3", "missed"),
        ],
    )


def check(rt, wav: bytes | None = None):
    return run_check(
        steps=STEPS,
        questions=QUESTIONS,
        clips={"q1": wav or tone_wav()},
        worker_lang="ta",
        supervisor_lang="en",
        runtime=rt,
    )


def audio_parts(seen) -> list[types.Part]:
    """The audio or file parts of one captured model request."""
    return [p for c in seen.contents for p in (c.parts or []) if p.inline_data or p.file_data]


def requests_by_node(llm) -> dict:
    """The captured model requests, by the node that sent them (told apart by their prompt)."""
    by_node = {}
    for seen in llm.seen:
        if seen.schema is TranscribeOut:
            by_node["blind_transcriber"] = seen
        elif prompts.JUDGE_WITH_AUDIO in seen.system:
            by_node["judge_a"] = seen
        elif prompts.JUDGE_NO_AUDIO in seen.system:
            by_node["judge_b"] = seen
    return by_node
