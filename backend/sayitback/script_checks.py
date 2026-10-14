"""Pure checks on what the model wrote: the script's step map, questions and length limits, the
back-translation alignment, and SOP quotes. "Code checks that every confirmed step is delivered
(stepMap) and asked about" (ARCHITECTURE.md, flow step 3) lives here, and so do the hard limits on
how much a script says (API.md, "Daily cap"): what is read aloud is what costs money.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sayitback.check_state import SENTENCE_SEPARATOR
from sayitback.guards import normalise
from sayitback.llm_schemas import BackOut, ScriptOut
from sayitback.models import Question, Script, Step
from sayitback.settings import Settings

SOP_LINE_MATCH = 0.85


@dataclass(frozen=True)
class ScriptLimits:
    """The hard bounds on a script's length. The prompt asks for short sentences, but a crafted
    instruction or SOP can talk the model out of that, so code enforces the bounds."""

    sentences_per_step: int
    line_chars: int

    @classmethod
    def from_settings(cls, s: Settings) -> ScriptLimits:
        return cls(sentences_per_step=s.max_sentences_per_step, line_chars=s.max_line_chars)


@dataclass
class ScriptDraft:
    script: Script
    hard: list[str] = field(default_factory=list)  # a step is not delivered or asked, or too long
    soft: list[str] = field(default_factory=list)  # fewer questions than the allowed range


def clean(text: str) -> str:
    return " ".join(text.split())


def build_script(
    out: ScriptOut,
    scope: Sequence[Step],
    *,
    first_qnum: int,
    q_range: tuple[int, int],
    limits: ScriptLimits,
) -> ScriptDraft:
    """Turn the model's output into a Script for `scope` and list what is wrong with it."""
    ids = {s.id for s in scope}
    sentences = [c for c in (clean(s) for s in out.sentences) if c]
    step_map: dict[str, list[int]] = {}
    for entry in out.step_map:
        valid = sorted({i for i in entry.sentence_indices if 0 <= i < len(sentences)})
        if entry.step_id in ids and valid:
            step_map[entry.step_id] = valid
    speakable = {s.id for s in scope if s.speakable}
    questions = _questions(out, ids, speakable, first_qnum)
    script = Script(
        instruction=SENTENCE_SEPARATOR.join(sentences),
        questions=questions,
        step_map=step_map,
        closing=clean(out.closing),
    )
    draft = ScriptDraft(script=script)
    _problems(draft, sentences, scope, speakable, q_range, limits)
    return draft


def _questions(out: ScriptOut, ids: set[str], speakable: set[str], first: int) -> list[Question]:
    questions: list[Question] = []
    for q in out.questions:
        step_ids = [sid for sid in dict.fromkeys(q.step_ids) if sid in ids and sid in speakable]
        text = clean(q.text)
        if text and step_ids:
            questions.append(
                Question(id=f"q{first + len(questions)}", text=text, step_ids=step_ids)
            )
    return questions


def _problems(
    draft: ScriptDraft,
    sentences: list[str],
    scope: Sequence[Step],
    speakable: set[str],
    q_range: tuple[int, int],
    limits: ScriptLimits,
) -> None:
    script = draft.script
    if not sentences:
        draft.hard.append("No instruction sentences were written.")
    if not script.closing:
        draft.hard.append("The closing is empty.")
    asked = {sid for q in script.questions for sid in q.step_ids}
    for step in scope:
        if step.id not in script.step_map:
            draft.hard.append(f"Step {step.id} is not delivered by any sentence (step_map).")
        if step.id in speakable and step.id not in asked:
            draft.hard.append(f"Step {step.id} is not checked by any question.")
    _length_problems(draft, sentences, scope, limits)
    _question_count(draft, q_range)


def _length_problems(
    draft: ScriptDraft, sentences: list[str], scope: Sequence[Step], limits: ScriptLimits
) -> None:
    """The hard length limits. Each note names the exact limit: it goes back to the model."""
    per_step = limits.sentences_per_step
    for step in scope:
        used = len(draft.script.step_map.get(step.id, []))
        if used > per_step:
            draft.hard.append(
                f"Step {step.id} is delivered by {used} sentences; use at most {per_step} per step."
            )
    total = per_step * len(scope)
    if len(sentences) > total:  # a sentence that delivers no step still lengthens the read-out
        steps = f"{len(scope)} step" + ("" if len(scope) == 1 else "s")
        draft.hard.append(
            f"The instruction has {len(sentences)} sentences; use at most {total} in all "
            f"({per_step} per step, {steps}), counting every sentence."
        )
    long = _too_long(draft.script, sentences, limits.line_chars)
    if long:
        draft.hard.append(
            f"Over {limits.line_chars} characters: {', '.join(long)}. Every sentence (numbered "
            f"from 0), question and the closing may have at most {limits.line_chars} characters."
        )


def _too_long(script: Script, sentences: list[str], limit: int) -> list[str]:
    """The spoken lines with more than `limit` characters, named by position or id."""
    found = [f"sentence {i}" for i, s in enumerate(sentences) if len(s) > limit]
    found += [f"question {q.id}" for q in script.questions if len(q.text) > limit]
    return [*found, "the closing"] if len(script.closing) > limit else found


def _question_count(draft: ScriptDraft, q_range: tuple[int, int]) -> None:
    """More questions than the range is a hard problem; fewer stays soft, because every step is
    still delivered and asked about."""
    low, high = q_range
    count = len(draft.script.questions)
    if count > high:
        draft.hard.append(f"Write at most {high} questions, not {count}.")
    elif count < low:
        draft.soft.append(f"Write between {low} and {high} questions, not {count}.")


def with_back_translation(script: Script, back: BackOut) -> Script:
    """Attach the back-translation, aligned by sentence index and by question id."""
    by_id = {q.id: clean(q.text) for q in back.questions}
    sentences = [clean(s) for s in back.sentences]
    return script.model_copy(
        update={
            "instruction_back_translation": SENTENCE_SEPARATOR.join(sentences),
            "questions": [
                q.model_copy(update={"back_translation": by_id.get(q.id, "")})
                for q in script.questions
            ],
        }
    )


def _window_ratio(norm_quote: str, norm_line: str) -> float:
    """How well the quote matches some run of words in the line (a quote is part of a line)."""
    wanted, words = norm_quote.split(), norm_line.split()
    best = 0.0
    for size in range(max(1, len(wanted) - 2), len(wanted) + 3):
        for i in range(max(1, len(words) - size + 1)):
            window = " ".join(words[i : i + size])
            best = max(best, SequenceMatcher(None, norm_quote, window).ratio())
    return best


def verified_sop_quote(quote: str | None, sop_text: str) -> str | None:
    """A SOP quote must be verbatim: keep it if it is in the SOP, else use the closest SOP line."""
    wanted = (quote or "").strip()
    if not wanted:
        return None
    if wanted in sop_text:
        return wanted
    lines = [ln.strip() for ln in sop_text.splitlines() if ln.strip()]
    norm = normalise(wanted)
    for line in lines:
        if norm and norm in normalise(line):
            return line
    scored = [(_window_ratio(norm, normalise(line)), line) for line in lines]
    ratio, best = max(scored, default=(0.0, ""))
    return best if ratio >= SOP_LINE_MATCH else None
