"""Guard rules 1-7 (API.md, "Guard rules"): pure functions, no model, no I/O.

The guard node (guard_node.py) of the `check_answer` workflow calls `run_guards`. Everything here is
unit-tested.
A step is `covered` only when both judges agree, the quote is really in a transcript, the
language is right, there was speech and the judges were confident. Anything else abstains.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from sayitback.models import (
    SEVERITY,
    NextAction,
    Question,
    Rating,
    Script,
    Step,
    Transcript,
)
from sayitback.wav import ClipStats

Range = tuple[int, int]
UNCLEAR_MARK = "[unclear]"
LATIN_RANGES: tuple[Range, ...] = ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F))
ELLIPSIS = re.compile(r"\.{3}|…|\[\.\.\.\]")
STEP_VERDICTS = tuple(SEVERITY)


@dataclass(frozen=True)
class GuardConfig:
    min_confidence: float = 0.75  # rule 3
    min_clip_seconds: float = 0.8  # rule 5
    silence_rms: float = 150.0  # rule 5, int16 RMS of the loudest 100 ms
    worker_share_floor: float = 0.30  # rule 4: under this share of worker-script letters ...
    other_share_ceiling: float = 0.50  # ... and over this share of another script or Latin
    min_quote_chars: int = 2
    passes: int = 2  # SIB_JUDGE_PASSES: with 2, a missing judge B output is all `unclear`


class GuardResult(BaseModel):
    transcripts: list[Transcript]
    pass_a: list[Rating]
    pass_b: list[Rating]
    ratings: list[Rating]
    next_action: NextAction


# Text helpers ----------------------------------------------------------------------------------


def normalise(text: str) -> str:
    """NFKC, casefold, drop punctuation, symbols and format marks, collapse whitespace."""
    kept = (
        ch
        for ch in unicodedata.normalize("NFKC", text).casefold()
        if unicodedata.category(ch)[0] not in "PS" and unicodedata.category(ch) != "Cf"
    )
    return " ".join("".join(kept).split())


def _in_ranges(cp: int, ranges: Iterable[Range]) -> bool:
    return any(lo <= cp <= hi for lo, hi in ranges)


def script_shares(text: str, worker_ranges: Sequence[Range]) -> tuple[float, float, float]:
    """Shares of letters in (worker script, Latin, any other script); all zero if no letters."""
    worker = latin = other = 0
    for ch in text.replace(UNCLEAR_MARK, " "):
        if unicodedata.category(ch)[0] not in "LM":
            continue
        cp = ord(ch)
        if _in_ranges(cp, worker_ranges):
            worker += 1
        elif _in_ranges(cp, LATIN_RANGES):
            latin += 1
        else:
            other += 1
    total = worker + latin + other
    return (0.0, 0.0, 0.0) if total == 0 else (worker / total, latin / total, other / total)


def is_language_mismatch(text: str, worker_ranges: Sequence[Range], cfg: GuardConfig) -> bool:
    """Rule 4: under 30 % worker-script letters and over 50 % Latin or another script."""
    worker, latin, other = script_shares(text, worker_ranges)
    if worker == latin == other == 0.0:
        return False
    return worker < cfg.worker_share_floor and (
        latin > cfg.other_share_ceiling or other > cfg.other_share_ceiling
    )


def quote_fragments(quote: str) -> list[str]:
    """A quote may join worker phrases with an ellipsis; each phrase must be verbatim."""
    parts = [normalise(p) for p in ELLIPSIS.split(quote)]
    return [p for p in parts if p]


def transcripts_with_quote(
    quote: str | None, transcripts: Sequence[Transcript], cfg: GuardConfig
) -> list[int]:
    """Indices of transcripts whose normalised `original` contains every phrase of the quote."""
    fragments = quote_fragments(quote or "")
    if not fragments or any(len(f) < cfg.min_quote_chars for f in fragments):
        return []
    haystacks = [normalise(t.original) for t in transcripts]
    return [i for i, h in enumerate(haystacks) if all(f in h for f in fragments)]


# Transcript flags (rules 4 and 5, per clip) ----------------------------------------------------


def flag_transcript(
    t: Transcript,
    stats: ClipStats | None,
    worker_ranges: Sequence[Range],
    cfg: GuardConfig,
) -> Transcript:
    """Add `no_speech` and `language_mismatch`. Model-supplied flags are kept."""
    flags = list(t.flags)
    spoken = t.original.replace(UNCLEAR_MARK, " ").strip()
    silent = (
        not spoken
        or "no_speech" in flags
        or (stats is not None and stats.duration_s < cfg.min_clip_seconds)
        or (stats is not None and stats.peak_rms < cfg.silence_rms)
    )
    if silent and "no_speech" not in flags:
        flags.append("no_speech")
    if not silent and is_language_mismatch(t.original, worker_ranges, cfg):
        flags.append("language_mismatch")
    return t.model_copy(update={"flags": flags})


def has_flag(t: Transcript, flag: str) -> bool:
    return flag in t.flags


# One pass and the combination (rule 1) ---------------------------------------------------------


def _clean_verdict(value: Any) -> str:
    return value if value in STEP_VERDICTS else "unclear"


def _clean_confidence(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def normalise_pass(raw: Mapping[str, Any] | None, steps: Sequence[Step]) -> list[Rating]:
    """One Rating per step. A missing or malformed rating becomes `unclear` with confidence 0."""
    by_step: dict[Any, Mapping[str, Any]] = {}
    for r in (raw or {}).get("ratings", []):
        if not isinstance(r, dict):
            continue
        kept = by_step.get(r.get("step_id"))
        if (
            kept is None
            or SEVERITY.get(_clean_verdict(r.get("verdict")), 1)
            > SEVERITY[_clean_verdict(kept.get("verdict"))]
        ):
            by_step[r.get("step_id")] = r  # a judge that rates a step twice is held to its worst
    ratings = []
    for step in steps:
        r = by_step.get(step.id) or {}
        ratings.append(
            Rating(
                step_id=step.id,
                verdict=_clean_verdict(r.get("verdict")),
                quote=(r.get("quote") or None),
                quote_translation=(r.get("quote_translation") or None),
                reason=str(r.get("reason") or ""),
                confidence=_clean_confidence(r.get("confidence")) if r else 0.0,
                flags=[],
            )
        )
    return ratings


@dataclass
class _Work:
    step_id: str
    verdict: str
    quotes: list[tuple[str, str | None]]  # (quote, translation), preferred first
    reason: str
    flags: list[str]
    confidences: list[float]

    def downgrade(self, flag: str, *, drop_quote: bool = False) -> None:
        self.verdict = "unclear"
        if flag not in self.flags:
            self.flags.append(flag)
        if drop_quote:
            self.quotes = []


def combine(a: Rating, b: Rating | None) -> _Work:
    """Rule 1: the more severe verdict wins; differing verdicts add `passes_disagreed`."""
    passes = [a] if b is None else [a, b]
    worst = max(passes, key=lambda r: SEVERITY[r.verdict])  # ties keep pass A
    flags = ["passes_disagreed"] if b is not None and a.verdict != b.verdict else []
    ordered = sorted(passes, key=lambda r: r is not worst)  # the winning pass's quote first
    return _Work(
        step_id=a.step_id,
        verdict=worst.verdict,
        quotes=[
            (r.quote, r.quote_translation)
            for r in ordered
            if r.quote and r.verdict == worst.verdict
        ],
        reason=worst.reason,
        flags=flags,
        confidences=[r.confidence if r.confidence is not None else 0.0 for r in passes],
    )


# The guard rules, one function each ------------------------------------------------------------


def _rule2_quote(w: _Work, transcripts: Sequence[Transcript], cfg: GuardConfig) -> list[int]:
    """Quote must be a verbatim substring of a transcript. Returns the transcripts holding it."""
    for quote, translation in w.quotes:
        found = transcripts_with_quote(quote, transcripts, cfg)
        if found:
            w.quotes = [(quote, translation)]
            return found
    needs_quote = w.verdict in ("covered", "contradicted")
    w.quotes = []
    if needs_quote:
        w.downgrade("quote_not_found")
    return []


def _rule3_confidence(w: _Work, cfg: GuardConfig) -> None:
    if w.verdict == "covered" and min(w.confidences) < cfg.min_confidence:
        w.downgrade("low_confidence")


def _rule4_language(w: _Work, found: list[int], transcripts: Sequence[Transcript]) -> None:
    if (
        w.verdict == "covered"
        and found
        and all(has_flag(transcripts[i], "language_mismatch") for i in found)
    ):
        w.downgrade("language_mismatch")


def _rule5_no_speech(
    w: _Work, found: list[int], asked: list[int], transcripts: Sequence[Transcript]
) -> None:
    if (
        w.verdict == "covered"
        and found
        and all(has_flag(transcripts[i], "no_speech") for i in found)
    ):
        w.downgrade("no_speech")
    if asked and all(has_flag(transcripts[i], "no_speech") for i in asked):
        w.downgrade("no_speech")


def _rule6_not_asked(w: _Work, is_asked: bool) -> None:
    if not is_asked:
        w.downgrade("not_asked", drop_quote=True)


def _step_is_asked(step: Step, questions: Sequence[Question], script: Script | None) -> bool:
    if not any(step.id in q.step_ids for q in questions):
        return False
    return not (script and script.step_map and not script.step_map.get(step.id))


def _freeze(w: _Work) -> Rating:
    quote, translation = w.quotes[0] if w.quotes else (None, None)
    return Rating(
        step_id=w.step_id,
        verdict=w.verdict,  # type: ignore[arg-type]
        quote=quote,
        quote_translation=translation,
        reason=w.reason,
        confidence=None,
        flags=list(dict.fromkeys(w.flags)),
    )


def guard_step(
    step: Step,
    a: Rating,
    b: Rating | None,
    *,
    transcripts: Sequence[Transcript],
    questions: Sequence[Question],
    script: Script | None,
    cfg: GuardConfig,
) -> Rating:
    w = combine(a, b)
    found = _rule2_quote(w, transcripts, cfg)
    _rule3_confidence(w, cfg)
    _rule4_language(w, found, transcripts)
    asked_ids = {q.id for q in questions if step.id in q.step_ids}
    asked = [i for i, t in enumerate(transcripts) if t.question_id in asked_ids]
    _rule5_no_speech(w, found, asked, transcripts)
    _rule6_not_asked(w, _step_is_asked(step, questions, script))
    return _freeze(w)


def run_guards(
    *,
    steps: Sequence[Step],
    questions: Sequence[Question],
    transcripts: Sequence[Transcript],
    raw_a: Mapping[str, Any] | None,
    raw_b: Mapping[str, Any] | None,
    stats: Mapping[str, ClipStats],
    worker_ranges: Sequence[Range],
    cfg: GuardConfig,
    script: Script | None = None,
) -> GuardResult:
    """Apply rules 1-7 and return the transcripts (with flags), both passes and final ratings."""
    flagged = [
        flag_transcript(t, stats.get(t.question_id), worker_ranges, cfg) for t in transcripts
    ]
    pass_a = normalise_pass(raw_a, steps)
    pass_b = normalise_pass(raw_b, steps) if cfg.passes >= 2 else []
    ratings = [
        guard_step(
            step,
            pass_a[i],
            pass_b[i] if pass_b else None,
            transcripts=flagged,
            questions=questions,
            script=script,
            cfg=cfg,
        )
        for i, step in enumerate(steps)
    ]
    done = all(r.verdict == "covered" for r in ratings)  # rule 7
    return GuardResult(
        transcripts=flagged,
        pass_a=pass_a,
        pass_b=pass_b,
        ratings=ratings,
        next_action="decide" if done else "reexplain",
    )
