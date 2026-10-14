"""`run_check`: the check workflow as one async call (API.md, "Check workflow").

It runs the ADK agent `check_answer` (a Workflow: blind transcriber, two judges in parallel,
a join, then the guard node) in a Runner built for this call. The eval harness imports it:

    from sayitback.pipeline import run_check
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from google.genai import types

from sayitback import catalog
from sayitback.adk_run import PhaseRun, run_phase
from sayitback.agents.check_answer.agent import NAME, build_agent
from sayitback.check_state import FINAL_KEY
from sayitback.errors import Unprocessable, UpstreamError, quote
from sayitback.guards import GuardResult
from sayitback.models import CheckResult, Question, Script, Step
from sayitback.runtime import BeforeCall, Runtime, get_runtime
from sayitback.wav import WavError, clip_stats, parse_wav

CHECK_META_KEYS = {"blind_transcriber": "transcribe", "judge_a": "judge_a", "judge_b": "judge_b"}

__all__ = ["CheckResult", "Question", "Script", "Step", "run_check"]


def _models(items: Sequence[Any], model: type) -> list[Any]:
    return [i if isinstance(i, model) else model.model_validate(i) for i in items]


def _validate(
    steps: list[Step], questions: list[Question], clips: Mapping[str, bytes], echo: int
) -> None:
    """`echo` is how much of a submitted clip name an error may quote (Settings.max_echo_chars)."""
    if not steps:
        raise Unprocessable("At least one step is required.")
    if len({s.id for s in steps}) != len(steps):
        raise Unprocessable("Step ids must be unique.")
    known = {q.id for q in questions}
    unknown = sorted(set(clips) - known)
    if unknown:
        names = ", ".join(quote(name, echo) for name in unknown)
        raise Unprocessable(f"Clips for unknown questions: {names}.")
    if not clips:
        raise Unprocessable("At least one clip is required.")


def _clip_inputs(
    questions: list[Question], clips: Mapping[str, bytes]
) -> tuple[list[str], dict[str, dict[str, float]], list[types.Part]]:
    ids, stats, parts = [], {}, []
    for q in questions:
        data = clips.get(q.id)
        if data is None:
            continue
        try:
            info = parse_wav(data)
        except WavError as exc:
            raise Unprocessable(f"Clip {q.id}: {exc}", code="invalid_audio") from exc
        s = clip_stats(data, info)
        ids.append(q.id)
        stats[q.id] = {"duration_s": s.duration_s, "peak_rms": s.peak_rms}
        parts += [
            types.Part(text=f"Clip for question {q.id}:"),
            types.Part.from_bytes(data=data, mime_type="audio/wav"),
        ]
    return ids, stats, parts


def _result(run: PhaseRun) -> CheckResult:
    raw = run.state.get(FINAL_KEY)
    if not raw:
        raise UpstreamError("The check produced no result.")
    final = GuardResult.model_validate(raw)
    audit = run.audit
    timings = {CHECK_META_KEYS.get(k, k): v for k, v in audit.latency_ms.items()}
    timings["check_total"] = audit.total_ms
    return CheckResult(
        transcripts=final.transcripts,
        pass_a=final.pass_a,
        pass_b=final.pass_b,
        ratings=final.ratings,
        next_action=final.next_action,
        model_ids={CHECK_META_KEYS.get(k, k): v for k, v in audit.model_ids.items()},
        timings_ms=timings,
    )


async def run_check(
    *,
    steps: list[Step],
    questions: list[Question],
    clips: dict[str, bytes],
    worker_lang: str,
    supervisor_lang: str,
    script: Script | None = None,
    live_input_transcripts: dict[str, str] | None = None,
    runtime: Runtime | None = None,
    before_call: BeforeCall | None = None,
) -> CheckResult:
    """Check the worker's answers against the steps in scope.

    `clips` maps question id to WAV bytes. `live_input_transcripts` (what Gemini Live heard) is
    accepted for the live path and is evidence only: it never reaches the judges and never
    changes a rating. `runtime` is for tests; the default is built from the environment.
    `before_call` is awaited once the inputs are validated, just before the first model call; the
    HTTP API reserves the daily Gemini cap there (it may raise to refuse). `eval/` passes none, so
    the cap never applies to it.
    """
    del live_input_transcripts
    rt = runtime or get_runtime()
    steps, questions = _models(steps, Step), _models(questions, Question)
    script = Script.model_validate(script) if isinstance(script, Mapping) else script
    catalog.require_lang(worker_lang, "worker_lang")
    catalog.require_lang(supervisor_lang, "supervisor_lang")
    _validate(steps, questions, clips, rt.settings.max_echo_chars)
    clip_ids, stats, parts = _clip_inputs(questions, clips)
    phase_input = {
        "steps": [s.model_dump(mode="json") for s in steps],
        "questions": [q.model_dump(mode="json") for q in questions],
        "script": script.model_dump(mode="json") if script else None,
        "worker_lang": worker_lang,
        "supervisor_lang": supervisor_lang,
        "worker_lang_name": catalog.lang_name(worker_lang),
        "supervisor_lang_name": catalog.lang_name(supervisor_lang),
        "lang_codes": list(catalog.lang_codes()),
        "clip_ids": clip_ids,
        "clip_stats": stats,
    }
    if before_call is not None:
        await before_call()
    run = await run_phase(rt, build_agent(rt), app_name=NAME, phase_input=phase_input, parts=parts)
    return _result(run)
