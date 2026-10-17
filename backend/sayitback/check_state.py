"""Session-state shapes for the check workflow, shared by the pipeline, the judges and the guard.

State key `input` holds the check input (snake_case dicts); the agents write `transcribe_out`,
`judge_a_out`, `judge_b_out` and `final`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sayitback.models import Question, Script, Step, Transcript
from sayitback.wav import ClipStats

TRANSCRIBE_KEY = "transcribe_out"
JUDGE_A_KEY = "judge_a_out"
JUDGE_B_KEY = "judge_b_out"
FINAL_KEY = "final"
TRANSCRIBER, JUDGE_A, JUDGE_B = "blind_transcriber", "judge_a", "judge_b"  # the model nodes
MODEL_REFUSED = "model_refused"  # the model's filter blocked the reply about this clip (v0.5.1)
SENTENCE_SEPARATOR = "\n"  # Script.instruction holds one sentence per line; stepMap indexes lines


def sentences_of(instruction: str) -> list[str]:
    return [line for line in instruction.split(SENTENCE_SEPARATOR) if line.strip()]


def script_view(script: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """What the judges see of the delivered script: its sentences and which deliver which step."""
    if not script:
        return None
    return {
        "sentences": sentences_of(script.get("instruction", "")),
        "step_map": dict(script.get("step_map") or {}),
    }


def question_ids(inp: Mapping[str, Any]) -> list[str]:
    return [q["id"] for q in inp.get("questions", [])]


def empty_transcript(question_id: str) -> Transcript:
    """A question with no usable recording: nothing was said, so nothing can be covered by it."""
    return Transcript(
        question_id=question_id,
        original="",
        detected_lang="none",
        translation="",
        flags=["no_speech"],
    )


def refused_transcript(question_id: str) -> Transcript:
    """A clip the transcriber's reply was blocked for: the worker may well have spoken, but there is
    nothing to quote, so nothing can be covered by it."""
    return empty_transcript(question_id).model_copy(update={"flags": [MODEL_REFUSED]})


def transcripts_from(
    out: Mapping[str, Any] | None,
    ids: Sequence[str],
    clip_ids: Sequence[str] | None = None,
    *,
    refused: bool = False,
) -> list[Transcript]:
    """One Transcript per question id, in question order. Only a clip that was uploaded
    (`clip_ids`) can have a transcript: anything the model returns for another id is dropped, so
    it can never be quoted as evidence. A clip the model skipped, and a question with no clip,
    become empty `no_speech` transcripts. When the transcriber's reply was blocked (`refused`),
    each uploaded clip becomes an empty `model_refused` transcript instead."""
    allowed = set(ids if clip_ids is None else clip_ids) & set(ids)
    if refused:
        return [refused_transcript(q) if q in allowed else empty_transcript(q) for q in ids]
    seen: dict[str, Transcript] = {}
    for item in (out or {}).get("transcripts", []):
        qid = item.get("question_id")
        if qid in allowed and qid not in seen:
            seen[qid] = Transcript(
                question_id=qid,
                original=str(item.get("original") or ""),
                detected_lang=str(item.get("detected_lang") or "none"),
                translation=str(item.get("translation") or ""),
                flags=[str(f) for f in item.get("flags") or []],
            )
    return [seen.get(qid) or empty_transcript(qid) for qid in ids]


class CheckInput:
    """The check input parsed from state into models."""

    def __init__(self, raw: Mapping[str, Any]) -> None:
        self.raw = raw
        self.steps = [Step.model_validate(s) for s in raw["steps"]]
        self.questions = [Question.model_validate(q) for q in raw["questions"]]
        script = raw.get("script")
        self.script = Script.model_validate(script) if script else None
        self.stats = {k: ClipStats(**v) for k, v in (raw.get("clip_stats") or {}).items()}
        self.worker_lang: str = raw["worker_lang"]
        self.ids = question_ids(raw)
        self.clip_ids: list[str] | None = raw.get("clip_ids")
