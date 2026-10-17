"""The model phases before and after the check: extract, script (+ back-translation), re-explain,
the supervisor's speech-to-text and a worker's spoken hazard report. Each runs one ADK agent in its
own Runner (adk_run).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from google.genai import types

from sayitback import catalog
from sayitback.adk_common import any_refusal
from sayitback.adk_run import PhaseRun, run_phase
from sayitback.agents.back_translate.agent import OUTPUT_KEY as BACK_KEY
from sayitback.agents.back_translate.agent import build_agent as build_back_translate
from sayitback.agents.extract_steps.agent import OUTPUT_KEY as EXTRACT_KEY
from sayitback.agents.extract_steps.agent import build_agent as build_extract
from sayitback.agents.hazard_report.agent import OUTPUT_KEY as HAZARD_KEY
from sayitback.agents.hazard_report.agent import build_agent as build_hazard_report
from sayitback.agents.re_explain.agent import OUTPUT_KEY as REEXPLAIN_KEY
from sayitback.agents.re_explain.agent import build_agent as build_re_explain
from sayitback.agents.transcribe_instruction.agent import OUTPUT_KEY as TRANSCRIPT_KEY
from sayitback.agents.transcribe_instruction.agent import build_agent as build_transcribe
from sayitback.agents.write_script.agent import OUTPUT_KEY as SCRIPT_KEY
from sayitback.agents.write_script.agent import build_agent as build_write_script
from sayitback.errors import UpstreamError
from sayitback.llm_schemas import (
    BackOut,
    ExtractOut,
    HazardOut,
    ReExplainOut,
    ScriptOut,
    SpokenText,
)
from sayitback.models import Conflict, Rating, Script, Sop, Step
from sayitback.runtime import BeforeCall, Runtime
from sayitback.script_checks import (
    ScriptDraft,
    ScriptLimits,
    build_script,
    clean,
    verified_sop_quote,
    with_back_translation,
)

log = logging.getLogger("sayitback.phases")
Q_RANGE = {"initial": (2, 3), "reexplain": (1, 2)}
META_KEYS = {
    "extract_steps": "extract",
    "write_script": "script",
    "back_translate": "back_translate",
    "re_explain": "re_explain",
    "transcribe_instruction": "transcribe_instruction",
    "hazard_report": "hazard_report",
}
NO_SPEECH_LANGS = ("other", "none")


@dataclass
class Meta:
    """Model ids (as the API returned them) and timings per phase, merged into the Round."""

    model_ids: dict[str, str] = field(default_factory=dict)
    timings_ms: dict[str, float] = field(default_factory=dict)

    def add(self, run: PhaseRun) -> None:
        for agent, model in run.audit.model_ids.items():
            self.model_ids[META_KEYS.get(agent, agent)] = model
        for agent, ms in run.audit.latency_ms.items():
            key = META_KEYS.get(agent, agent)
            self.timings_ms[key] = round(self.timings_ms.get(key, 0.0) + ms, 1)


# A phase whose reply the model's safety filter blocked (adk_common.record_refusal): what the user
# is told instead of "no result" (v0.5.1). The check is not here: its guard flags `model_refused`.
REFUSED_MESSAGES = {
    "transcribe_instruction": (
        "The model could not process this recording. Record it again, or type the instruction."
    ),
    "hazard_report": (
        "The model could not process this report. Report it with a tap instead, or tell your "
        "supervisor in person."
    ),
}
REFUSED_MESSAGE = "The model could not process this request. Try again, or change the wording."


def _result(run: PhaseRun, key: str, schema: type) -> Any:
    raw = run.state.get(key)
    if not raw:
        if any_refusal(run.state):
            raise UpstreamError(REFUSED_MESSAGES.get(run.audit.phase, REFUSED_MESSAGE))
        raise UpstreamError("The model returned no result.")
    return schema.model_validate(raw)


def _lang_inputs(supervisor_lang: str, worker_lang: str | None = None) -> dict[str, Any]:
    out = {
        "supervisor_lang": supervisor_lang,
        "supervisor_lang_name": catalog.lang_name(supervisor_lang),
    }
    if worker_lang:
        out |= {"worker_lang": worker_lang, "worker_lang_name": catalog.lang_name(worker_lang)}
    return out


# Extract ---------------------------------------------------------------------------------------


async def extract_steps(
    rt: Runtime, *, instruction: str, supervisor_lang: str, sop: Sop
) -> tuple[list[Step], list[Conflict], Meta]:
    inp = {
        **_lang_inputs(supervisor_lang),
        "instruction": instruction,
        "sop": sop.model_dump(mode="json"),
        "max_steps": rt.settings.max_steps,
    }
    run = await run_phase(rt, build_extract(rt), app_name="extract_steps", phase_input=inp)
    out: ExtractOut = _result(run, EXTRACT_KEY, ExtractOut)
    steps = _steps_from(out, sop, rt.settings.max_steps)
    if not steps:
        raise UpstreamError("No critical steps could be extracted. Edit the instruction and retry.")
    conflicts = [
        Conflict(
            step_id=f"s{c.step_number}" if 1 <= c.step_number <= len(steps) else None,
            message=clean(c.message),
        )
        for c in out.conflicts
        if clean(c.message)
    ]
    meta = Meta()
    meta.add(run)
    return steps, conflicts, meta


def _steps_from(out: ExtractOut, sop: Sop, limit: int) -> list[Step]:
    steps = []
    for item in out.steps:
        text = clean(item.text)
        if not text or len(steps) >= limit:
            continue
        from_sop = item.source in ("sop", "both")
        steps.append(
            Step(
                id=f"s{len(steps) + 1}",
                text=text,
                hazard=clean(item.hazard),
                essential=[e for e in (clean(x) for x in item.essential) if e],
                source=item.source,
                sop_quote=verified_sop_quote(item.sop_quote, sop.text) if from_sop else None,
                speakable=item.speakable,
            )
        )
    return steps


# Script and back-translation -------------------------------------------------------------------


async def make_script(
    rt: Runtime,
    *,
    steps: list[Step],
    basis: str,
    round_kind: str,
    supervisor_lang: str,
    worker_lang: str,
    site_id: str,
    first_qnum: int,
    previous_questions: list[str],
    before_retry: BeforeCall | None = None,
) -> tuple[Script, Meta]:
    """Write the worker-language script, code-check it (one retry), then back-translate it.

    `before_retry` is awaited just before the retry's model call, and may raise to refuse it: the
    HTTP API reserves the daily Gemini cap there (429 `daily_limit`, no retry call is made)."""
    q_range = Q_RANGE[round_kind]
    limits = ScriptLimits.from_settings(rt.settings)
    inp = {
        **_lang_inputs(supervisor_lang, worker_lang),
        "steps": [s.model_dump(mode="json") for s in steps],
        "basis": basis,
        "round_kind": round_kind,
        "site_context": catalog.site_context(site_id),
        "questions_min": q_range[0],
        "questions_max": q_range[1],
        "max_sentences_per_step": limits.sentences_per_step,
        "max_line_chars": limits.line_chars,
        "previous_questions": previous_questions,
    }
    meta = Meta()
    check = partial(
        build_script, scope=steps, first_qnum=first_qnum, q_range=q_range, limits=limits
    )
    script = await _write_checked(rt, inp, check, meta, before_retry)
    back_inp = {
        **_lang_inputs(supervisor_lang, worker_lang),
        "sentences": script.instruction.split("\n"),
        "questions": [{"id": q.id, "text": q.text} for q in script.questions],
    }
    run = await run_phase(
        rt, build_back_translate(rt), app_name="back_translate", phase_input=back_inp
    )
    meta.add(run)
    return with_back_translation(script, _result(run, BACK_KEY, BackOut)), meta


async def _write_checked(
    rt: Runtime,
    inp: dict[str, Any],
    check: Callable[[ScriptOut], ScriptDraft],
    meta: Meta,
    before_retry: BeforeCall | None,
) -> Script:
    """Write, check, and retry once with the problems named. A draft whose only fault is too few
    questions is acceptable: every step is delivered and asked about, within the limits. The retry
    is a model call like any other, so `before_retry` (the daily cap) runs just before it."""
    notes: list[str] = []
    fallback: Script | None = None
    for attempt in (1, 2):
        if attempt == 2 and before_retry is not None:
            await before_retry()
        run = await run_phase(
            rt,
            build_write_script(rt),
            app_name="write_script",
            phase_input={**inp, "fix_notes": notes},
        )
        meta.add(run)
        draft = check(_result(run, SCRIPT_KEY, ScriptOut))
        if not draft.hard and not draft.soft:
            return draft.script
        if not draft.hard:
            fallback = draft.script
        notes = [*draft.hard, *draft.soft]
        log.warning("script attempt %d had %d problems", attempt, len(notes))
    if fallback is not None:
        return fallback
    raise UpstreamError(
        "The script did not pass its checks (every step delivered and asked about, within the "
        "length limits).",
        code="script_incomplete",
    )


# Re-explain and the supervisor's speech-to-text ------------------------------------------------


async def explain(
    rt: Runtime,
    *,
    steps: list[Step],
    ratings: dict[str, Rating],
    supervisor_lang: str,
    sop_title: str,
) -> tuple[str, Meta]:
    rows = []
    for step in steps:
        rating = ratings.get(step.id)
        rows.append(
            {
                **step.model_dump(mode="json"),
                "verdict": rating.verdict if rating else "unclear",
                "reason": rating.reason if rating else "",
            }
        )
    inp = {**_lang_inputs(supervisor_lang), "steps": rows, "sop_title": sop_title}
    run = await run_phase(rt, build_re_explain(rt), app_name="re_explain", phase_input=inp)
    meta = Meta()
    meta.add(run)
    text = clean(_result(run, REEXPLAIN_KEY, ReExplainOut).explanation)
    if not text:
        raise UpstreamError("The model returned an empty re-explanation.")
    return text, meta


async def transcribe_instruction(rt: Runtime, audio: bytes, lang: str) -> str:
    inp = {"lang_name": catalog.lang_name(lang), "native": catalog.language_native(lang)}
    parts = [types.Part.from_bytes(data=audio, mime_type="audio/wav")]
    run = await run_phase(
        rt, build_transcribe(rt), app_name="transcribe_instruction", phase_input=inp, parts=parts
    )
    return clean(_result(run, TRANSCRIPT_KEY, SpokenText).text)


async def report_hazard(
    rt: Runtime, audio: bytes, *, worker_lang: str, supervisor_lang: str
) -> tuple[str, str, str]:
    """A worker's spoken hazard report: (original, detected language, translation). The original is
    verbatim in the worker's own script and the translation is in the supervisor's language."""
    inp = {
        "worker_lang_name": catalog.lang_name(worker_lang),
        "worker_native": catalog.language_native(worker_lang),
        "supervisor_lang_name": catalog.lang_name(supervisor_lang),
        "lang_codes": list(catalog.lang_codes()),
    }
    parts = [types.Part.from_bytes(data=audio, mime_type="audio/wav")]
    run = await run_phase(
        rt, build_hazard_report(rt), app_name="hazard_report", phase_input=inp, parts=parts
    )
    out: HazardOut = _result(run, HAZARD_KEY, HazardOut)
    original, translation = clean(out.original), clean(out.translation)
    if not original:
        return "", "none", ""
    lang = out.detected_lang.strip().lower()
    known = (*catalog.lang_codes(), *NO_SPEECH_LANGS)
    return original, lang if lang in known else "other", translation
