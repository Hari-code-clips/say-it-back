"""Guard rules 1-8 (API.md, "Guard rules"): pure functions, no model, no I/O.

The guard node (guard_node.py) of the `check_answer` workflow calls `run_guards` (rules 1-7).
Rule 8, the delivery rule, is `apply_delivery`: the round's check applies it after the workflow,
in live mode, so `run_check` and eval/ are unchanged. Everything here is unit-tested.
A step is `covered` only when both judges agree, the quote is really in a transcript, the
language is right, there was speech and the judges were confident. Anything else abstains.
v0.5: a quote's phrases must occur in order, without overlap, in one transcript, each weighing at
least 3 (`quote_weight`: letters only, not combining marks), and a `covered` quote at least 8 in
all. [unclear] marks are no one's words: they weigh nothing and no phrase matches across one. A
contradiction quoted from an answer that was speech stands even when the clip of the question
asking that step was silent.
v0.5.1: a clip whose transcription the model's filter blocked is `model_refused`, not `no_speech`
(the worker may well have spoken): a step asked only of such clips is `unclear` + `model_refused`,
and so is a step a blocked judge left unclear. Either way the reason is REFUSED_REASONS, in the
supervisor's language. Nothing a blocked reply touches can be `covered`.
v0.5.3: rule 1 no longer lets the more severe verdict win. Passes that agree stand, a
`contradicted` in either stands, and every other split is `unclear`, so one judge hearing nothing
(`missed`) cannot overrule one that heard the worker touch the step, and a split is never `covered`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel

from sayitback.check_state import MODEL_REFUSED
from sayitback.models import (
    SEVERITY,
    DeliveryCheck,
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
UNCLEAR_SPAN = re.compile(r"\[\s*unclear\b[^\]]*\]", re.IGNORECASE)  # after NFKC: ［ is [
LATIN_RANGES: tuple[Range, ...] = ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F))
# Han, Hiragana, Katakana and Hangul: one character carries about a word's worth of letters
WIDE_RANGES: tuple[Range, ...] = (
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x3040, 0x30FF),  # Hiragana, Katakana
    (0x3130, 0x318F),  # Hangul compatibility Jamo
    (0x31F0, 0x31FF),  # Katakana phonetic extensions
    (0x3400, 0x4DBF),  # CJK extension A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xA960, 0xA97F),  # Hangul Jamo extended A
    (0xAC00, 0xD7FF),  # Hangul syllables, Jamo extended B
    (0xF900, 0xFAFF),  # CJK compatibility ideographs
    (0xFF66, 0xFF9F),  # halfwidth Katakana
    (0x20000, 0x3134F),  # CJK extensions B to H
)
ELLIPSIS = re.compile(r"\.{3}|…|\[\.\.\.\]")
STEP_VERDICTS = tuple(SEVERITY)
DELIVERY_MISMATCH = "delivery_mismatch"
NO_SPEECH = "no_speech"
# What the supervisor reads for a step the model refused to process (v0.5.1). The ta and zh lines
# are DRAFT machine translations, pending native review. Other languages get the English.
REFUSED_REASONS: Mapping[str, str] = MappingProxyType(
    {
        "en": "The checker could not process this answer; ask again or check in person.",
        "ta": "சரிபார்ப்பால் இந்தப் பதிலைச் செயலாக்க முடியவில்லை; மீண்டும் கேளுங்கள் அல்லது நேரில் சரிபாருங்கள்.",
        "zh": "检查程序无法处理这个回答；请再问一次，或当面确认。",
    }
)


def refused_reason(supervisor_lang: str) -> str:
    return REFUSED_REASONS.get(supervisor_lang, REFUSED_REASONS["en"])


@dataclass(frozen=True)
class GuardConfig:
    min_confidence: float = 0.75  # rule 3
    min_clip_seconds: float = 0.8  # rule 5
    silence_rms: float = 150.0  # rule 5, int16 RMS of the loudest 100 ms
    worker_share_floor: float = 0.30  # rule 4: under this share of worker-script letters ...
    other_share_ceiling: float = 0.50  # ... and over this share of another script or Latin
    min_quote_weight: int = 3  # rule 2: each phrase of a quote (quote_weight)
    min_covered_quote_weight: int = 8  # rule 2: all the phrases of a `covered` quote together
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


def quote_weight(text: str) -> int:
    """How much a quote says: 2 per Han, kana or Hangul character, 1 per other letter. Combining
    marks (vowel signs, viramas, Burmese tone marks), spaces, punctuation, digits and symbols weigh
    0, so a Brahmic or Burmese word weighs about what its Latin spelling would."""
    return sum(
        2 if _in_ranges(ord(ch), WIDE_RANGES) else 1
        for ch in text
        if unicodedata.category(ch)[0] == "L"
    )


def _unmarked(text: str) -> list[str]:
    """The stretches of `text` between the transcriber's [unclear] marks (any case, spacing or
    bracket width): a mark is nobody's words."""
    return UNCLEAR_SPAN.split(unicodedata.normalize("NFKC", text))


def quote_fragments(quote: str) -> list[str]:
    """A quote may join worker phrases with an ellipsis; each phrase must be verbatim. An [unclear]
    mark in a quote only separates phrases."""
    parts = [normalise(p) for span in _unmarked(quote) for p in ELLIPSIS.split(span)]
    return [p for p in parts if p]


def _in_order(fragments: Sequence[str], spans: Sequence[str]) -> bool:
    """Every fragment occurs inside one span, each after the end of the one before (no overlap,
    and never across an [unclear] mark between two spans)."""
    span, start = 0, 0
    for fragment in fragments:
        while span < len(spans):
            at = spans[span].find(fragment, start)
            if at >= 0:
                start = at + len(fragment)
                break
            span, start = span + 1, 0
        else:
            return False
    return True


def transcripts_with_quote(
    quote: str | None, transcripts: Sequence[Transcript], cfg: GuardConfig
) -> list[int]:
    """Indices of transcripts whose normalised `original` holds every phrase of the quote, in the
    quote's order. A phrase lighter than `min_quote_weight` ("ok", "it") is in almost any answer,
    so a quote with one matches nothing. [unclear] marks are dropped from both sides first."""
    fragments = quote_fragments(quote or "")
    if not fragments or any(quote_weight(f) < cfg.min_quote_weight for f in fragments):
        return []
    haystacks = [[normalise(s) for s in _unmarked(t.original)] for t in transcripts]
    return [i for i, spans in enumerate(haystacks) if _in_order(fragments, spans)]


# Transcript flags (rules 4 and 5, per clip) ----------------------------------------------------


def flag_transcript(
    t: Transcript,
    stats: ClipStats | None,
    worker_ranges: Sequence[Range],
    cfg: GuardConfig,
) -> Transcript:
    """Add `no_speech` and `language_mismatch`. Model-supplied flags are kept. A `model_refused`
    clip's empty transcript is not silence: only its own length and level can make it so."""
    flags = list(t.flags)
    spoken = t.original.replace(UNCLEAR_MARK, " ").strip()
    silent = (
        (not spoken and MODEL_REFUSED not in flags)
        or "no_speech" in flags
        or (stats is not None and stats.duration_s < cfg.min_clip_seconds)
        or (stats is not None and stats.peak_rms < cfg.silence_rms)
    )
    if silent and "no_speech" not in flags:
        flags.append("no_speech")
    if not silent and is_language_mismatch(t.original, worker_ranges, cfg):
        flags.append("language_mismatch")
    return t.model_copy(update={"flags": flags})


def has_flag(t: Transcript, *flags: str) -> bool:
    """`t` carries any of `flags`."""
    return any(flag in t.flags for flag in flags)


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


# What a supervisor reads next to "Ask again" when the passes split without a contradiction. The
# pass that doubted speaks first: its words about the answer fit the chip. A covered pass's reason
# ("the worker states every element") would contradict it, so it is never shown, even when the
# doubting pass gave none (a blocked or missing judge B is an `unclear` pass with no reason).
# A covered pass's quote is still what the worker said, so it comes second as a quote.
SPLIT_QUOTE_ORDER = {"unclear": 0, "covered": 1, "missed": 2}
SPLIT_REASON_ORDER = ("unclear", "missed")


def rule1_verdict(a: str, b: str) -> str:
    """Two passes that agree give that verdict; either one `contradicted` gives `contradicted`;
    any other split is `unclear`, never `covered`."""
    if a == b:
        return a
    return "contradicted" if "contradicted" in (a, b) else "unclear"


def combine(a: Rating, b: Rating | None) -> _Work:
    """Rule 1: agreement stands, a contradiction in either pass stands, and any other split is
    `unclear`. Differing verdicts add `passes_disagreed`."""
    passes = [a] if b is None else [a, b]
    verdict = a.verdict if b is None else rule1_verdict(a.verdict, b.verdict)
    flags = ["passes_disagreed"] if b is not None and a.verdict != b.verdict else []
    if flags and verdict == "unclear":
        quoting = sorted(passes, key=lambda r: SPLIT_QUOTE_ORDER[r.verdict])
        reasons = (r.reason for v in SPLIT_REASON_ORDER for r in passes if r.verdict == v)
        reason = next((text for text in reasons if text), "")
    else:
        quoting = [r for r in passes if r.verdict == verdict]  # pass A first
        reason = quoting[0].reason
    return _Work(
        step_id=a.step_id,
        verdict=verdict,
        quotes=[(r.quote, r.quote_translation) for r in quoting if r.quote],
        reason=reason,
        flags=flags,
        confidences=[r.confidence if r.confidence is not None else 0.0 for r in passes],
    )


# The guard rules, one function each ------------------------------------------------------------


def _covering_weight(quote: str, cfg: GuardConfig) -> bool:
    return sum(map(quote_weight, quote_fragments(quote))) >= cfg.min_covered_quote_weight


def _rule2_quote(w: _Work, transcripts: Sequence[Transcript], cfg: GuardConfig) -> list[int]:
    """Quote must be verbatim in one transcript, its phrases in order, and a `covered` quote must
    weigh at least `min_covered_quote_weight` in all. Returns the transcripts holding it."""
    for quote, translation in w.quotes:
        found = transcripts_with_quote(quote, transcripts, cfg)
        if found and (w.verdict != "covered" or _covering_weight(quote, cfg)):
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
    """A silent clip covers nothing, and a step whose asking clips were all silent is unclear,
    unless it is a contradiction quoted from an answer that was speech: unsafe words the worker
    said stay on the record, whichever question they answered. A clip the model refused counts as
    unheard here, and names the flag (`model_refused`) unless one of them really was silent."""
    if (
        w.verdict == "covered"
        and found
        and all(has_flag(transcripts[i], "no_speech") for i in found)
    ):
        w.downgrade("no_speech")
    spoken_contradiction = w.verdict == "contradicted" and any(
        not has_flag(transcripts[i], "no_speech") for i in found
    )
    unheard = [i for i in asked if has_flag(transcripts[i], NO_SPEECH, MODEL_REFUSED)]
    if asked and len(unheard) == len(asked) and not spoken_contradiction:
        refused = any(
            has_flag(transcripts[i], MODEL_REFUSED) and not has_flag(transcripts[i], NO_SPEECH)
            for i in asked
        )
        w.downgrade(MODEL_REFUSED if refused else NO_SPEECH)


def _refused_judge(w: _Work, judge_refused: bool) -> None:
    """A blocked judge's pass is all `unclear`: a step it leaves unclear says why."""
    if judge_refused and w.verdict == "unclear" and MODEL_REFUSED not in w.flags:
        w.flags.append(MODEL_REFUSED)


def _rule6_not_asked(w: _Work, is_asked: bool) -> None:
    if not is_asked:
        w.downgrade("not_asked", drop_quote=True)


def _step_is_asked(step: Step, questions: Sequence[Question], script: Script | None) -> bool:
    if not any(step.id in q.step_ids for q in questions):
        return False
    return not (script and script.step_map and not script.step_map.get(step.id))


def _freeze(w: _Work, supervisor_lang: str = "en") -> Rating:
    quote, translation = w.quotes[0] if w.quotes else (None, None)
    refused = w.verdict == "unclear" and MODEL_REFUSED in w.flags
    return Rating(
        step_id=w.step_id,
        verdict=w.verdict,  # type: ignore[arg-type]
        quote=quote,
        quote_translation=translation,
        reason=refused_reason(supervisor_lang) if refused else w.reason,
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
    judge_refused: bool = False,
    supervisor_lang: str = "en",
) -> Rating:
    w = combine(a, b)
    found = _rule2_quote(w, transcripts, cfg)
    _rule3_confidence(w, cfg)
    _rule4_language(w, found, transcripts)
    asked_ids = {q.id for q in questions if step.id in q.step_ids}
    asked = [i for i, t in enumerate(transcripts) if t.question_id in asked_ids]
    _rule5_no_speech(w, found, asked, transcripts)
    _refused_judge(w, judge_refused)
    _rule6_not_asked(w, _step_is_asked(step, questions, script))
    return _freeze(w, supervisor_lang)


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
    refused_judges: Collection[str] = (),
    supervisor_lang: str = "en",
) -> GuardResult:
    """Apply rules 1-7 and return the transcripts (with flags), both passes and final ratings.
    `refused_judges` names the judges ("judge_a", "judge_b") whose reply the model's filter
    blocked; `supervisor_lang` is the language of the reason a refused step is given."""
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
            judge_refused=bool(refused_judges),
            supervisor_lang=supervisor_lang,
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


# Rule 8: what the worker heard ----------------------------------------------------------------


def next_action_for(ratings: Sequence[Rating]) -> NextAction:
    """Rule 7: decide only when every step in scope is covered."""
    return "decide" if all(r.verdict == "covered" for r in ratings) else "reexplain"


def delivery_affected_steps(
    delivery: Sequence[DeliveryCheck], questions: Sequence[Question], scope: Sequence[str]
) -> set[str]:
    """The steps a failed delivery check touches: `instruction` delivers every step in the round's
    scope, a question id the steps that question checks, and its `.reply` the steps of that
    question and of every later one (a hint said after q1's answer is heard before q2), `closing`
    none."""
    order = [q.id for q in questions]
    asks = {q.id: q.step_ids for q in questions}
    affected: set[str] = set()
    for check in delivery:
        if check.ok:
            continue
        if check.segment == "instruction":
            affected.update(scope)
        elif check.segment.endswith(".reply"):
            qid = check.segment.removesuffix(".reply")
            later = order[order.index(qid) :] if qid in order else []
            for q in later:
                affected.update(asks[q])
        elif check.segment != "closing":
            affected.update(asks.get(check.segment, []))
    return affected & set(scope)


def apply_delivery(
    ratings: Sequence[Rating],
    delivery: Sequence[DeliveryCheck],
    questions: Sequence[Question],
    scope: Sequence[str],
) -> tuple[list[Rating], NextAction]:
    """Rule 8 (live mode): a step rated `covered` whose delivery the check could not vouch for
    becomes `unclear` + `delivery_mismatch`: the worker may have heard something other than the
    approved script, or a hint. The quote and reason stay. `nextAction` is recomputed (rule 7)."""
    affected = delivery_affected_steps(delivery, questions, scope)
    out = []
    for r in ratings:
        if r.verdict == "covered" and r.step_id in affected:
            flags = list(dict.fromkeys([*r.flags, DELIVERY_MISMATCH]))
            r = r.model_copy(update={"verdict": "unclear", "flags": flags})
        out.append(r)
    return out, next_action_for(out)
