"""Live mode: compare what Gemini Live actually said with the approved script (API.md v0.4,
"Delivery check").

Per segment of the approved script ("instruction", each question, "closing"):
- `similarity` is the character-level ratio of the normalised texts, and `script_ok` says the speech
  is in the worker language's own script (it catches Odia drifting to Hindi);
- `issues` names what is wrong: `not_spoken`, `wrong_script`, `low_similarity` (under
  SIB_DELIVERY_MIN_SIMILARITY), `negation_changed` and `number_changed`. Similarity alone can never
  catch a dropped "not": a Tamil instruction without its `இல்லை` still scores 0.95.
- Negations are counted per sentence: each approved sentence is aligned with the said sentence most
  like it, and the language's negation markers must agree pair by pair and in total, so a "not"
  moved from one sentence to another is caught. Sentences that cannot be aligned fail safe. A said
  sentence that is a piece of one approved sentence must agree with it too, so an alignment
  misled by two sentences that start alike cannot hide the move.
- Numbers are compared in order, as a sequence (digit runs and the language's number words), so
  "15 m" against "50 m" in words (`十五米`, `五十米`) is caught.

A `"<qid>.reply"` segment (what Live said after that question's answer window) has no approved
text: it carries what was said, and it is not ok when its normalised text is longer than
SIB_REPLY_MAX_CHARS (`reply_too_long`) or when it repeats a word of the round's approved
instruction or questions that is not one of the language's thanks words (`reply_not_neutral`): the
voice may have said more than a neutral thanks, or a hint.

A check is `ok` only when it is spoken, in the worker's script, similar enough and has no issue.
Guard rule 8 (guards.apply_delivery) turns the steps a failed segment delivers into "Ask again".
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from difflib import SequenceMatcher

from sayitback.catalog import LanguageMarkers
from sayitback.guards import Range, normalise, script_shares
from sayitback.models import DeliveryCheck, DeliveryIssue, Script

INSTRUCTION = "instruction"
CLOSING = "closing"
REPLY_SUFFIX = ".reply"  # the briefer's speech after an answer window: no approved text
NUMBER = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
REPLY_SIMILARITY = 1.0  # a reply has nothing to be similar to (API.md: 1 for a ".reply" segment)


def segment_texts(script: Script) -> dict[str, str]:
    """Segment name -> the approved text: "instruction", each question id, "closing"."""
    return {
        INSTRUCTION: script.instruction,
        **{q.id: q.text for q in script.questions},
        CLOSING: script.closing,
    }


def similarity(said: str, expected: str) -> float:
    a, b = normalise(said), normalise(expected)
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b, autojunk=False).ratio(), 3)


# Counting negations and numbers ----------------------------------------------------------------

SENTENCE_END = re.compile(r"[!?।॥။。\n]+|(?<![0-9])\.|\.(?![0-9])")
DECIMAL = "\ue000"  # a private-use mark that `normalise` keeps, for the point inside "1.5"
NUMBER_RUN = re.compile(r"[0-9]+(?:\ue000[0-9]+)*")
TOKEN = re.compile(r"\S+")
ALIGN_MIN = 0.6  # below this share an approved sentence is in no said sentence: fail safe
PIECE_MIN = 0.8  # a said sentence this much inside one approved sentence is a piece of it
MIN_REPLY_WORD_LETTERS = 3


def _positions(norm: str, term: str, match: str) -> list[int]:
    """Where `term` (normalised) starts in `norm` (normalised): whole words for a "word" language,
    non-overlapping substrings otherwise."""
    if not term:
        return []
    if match != "word":
        found, start = [], 0
        while (i := norm.find(term, start)) != -1:
            found.append(i)
            start = i + len(term)
        return found
    tokens = [(m.start(), m.group()) for m in TOKEN.finditer(norm)]
    wanted = term.split()
    width = len(wanted)
    return [
        tokens[i][0]
        for i in range(len(tokens) - width + 1)
        if [t for _, t in tokens[i : i + width]] == wanted
    ]


def count_terms(text: str, terms: Iterable[str], match: str) -> Counter[str]:
    """Occurrences of each term in `text`; both are normalised with guards.normalise first."""
    norm = normalise(text)
    found: Counter[str] = Counter()
    for term in dict.fromkeys(normalise(t) for t in terms):
        n = len(_positions(norm, term, match))
        if n:
            found[term] = n
    return found


def ascii_digits(text: str) -> str:
    """Every decimal digit (Tamil ௧, Devanagari १, Bengali ১, Myanmar ၁, Odia ୧ ...) as ASCII."""
    out = []
    for ch in unicodedata.normalize("NFKC", text):
        value = unicodedata.decimal(ch, None) if not ch.isascii() else None
        out.append(str(value) if value is not None else ch)
    return "".join(out)


def _number_value(run: str) -> str:
    whole, _, fraction = run.replace(DECIMAL, ".").partition(".")
    whole = whole.lstrip("0") or "0"
    return f"#{whole}.{fraction}" if fraction else f"#{whole}"


def numbers(text: str, number_words: Iterable[str], match: str) -> list[str]:
    """The numbers in the order they are said: digit runs (native digits mapped to ASCII; "1,000"
    is 1000, "1.5" stays 1.5) and the language's number words, each where it starts."""
    prepared = re.sub(r"(?<=[0-9]),(?=[0-9])", "", ascii_digits(text))
    norm = normalise(re.sub(r"(?<=[0-9])\.(?=[0-9])", DECIMAL, prepared))
    found = [
        (m.start(), -len(m.group()), _number_value(m.group())) for m in NUMBER_RUN.finditer(norm)
    ]
    for term in dict.fromkeys(normalise(w) for w in number_words):
        found += [(at, -len(term), term) for at in _positions(norm, term, match)]
    return [label for *_, label in sorted(found)]


def negations(text: str, spec: LanguageMarkers) -> int:
    return sum(count_terms(text, spec.negation_markers, spec.match).values())


def sentences(text: str) -> list[str]:
    """Sentences, split on . ! ? । ॥ ။ 。 and line breaks (not on the point inside "1.5")."""
    parts = SENTENCE_END.split(unicodedata.normalize("NFKC", text))
    return [p for p in parts if normalise(p)]


def contained(approved: str, said: str) -> float:
    """How much of an approved sentence (normalised) the said sentence holds, 0..1. Unlike the
    similarity ratio it does not fall when Live joins two approved sentences into one."""
    a, b = normalise(approved), normalise(said)
    if not a or not b:
        return 0.0
    blocks = SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
    return sum(block.size for block in blocks) / len(a)


def negation_changed(said: str, expected: str, spec: LanguageMarkers) -> bool:
    """The totals differ, or an approved sentence and the said sentence aligned with it do (said
    sentences that two approved ones share are compared with their sum), or a sentence cannot be
    aligned at all, or an approved sentence and its pieces do (`_pieces_disagree`)."""
    if negations(said, spec) != negations(expected, spec):
        return True
    approved, heard = sentences(expected), sentences(said)
    if len(approved) <= 1 and len(heard) <= 1:
        return False
    if not heard:
        return True
    expected_at: dict[int, int] = {}
    targets: list[int] = []
    for line in approved:
        scores = [contained(line, h) for h in heard]
        best = max(range(len(heard)), key=scores.__getitem__)
        if scores[best] < ALIGN_MIN:
            return True
        targets.append(best)
        expected_at[best] = expected_at.get(best, 0) + negations(line, spec)
    if any(expected_at.get(i, 0) != negations(h, spec) for i, h in enumerate(heard)):
        return True
    return _pieces_disagree(approved, heard, targets, spec)


def _pieces_disagree(
    approved: list[str], heard: list[str], targets: list[int], spec: LanguageMarkers
) -> bool:
    """A said sentence that lies almost wholly (PIECE_MIN) inside one approved sentence, more than
    inside any other, is a piece of it, unless two approved sentences were joined into it. An
    approved sentence's pieces must hold its negations. This catches a "not" moved into the next
    sentence when the two start alike: "Never stand under the load. Stay outside ..." said as
    "Stand under the load. Never stay outside ..." aligns both approved sentences with the second
    said one, whose count then matches, while the first said sentence is a piece of the first
    approved one without its "never"."""
    shared = {j for j, n in Counter(targets).items() if n > 1}
    held: dict[int, int] = {}  # approved sentence -> negations in its pieces
    for j, line in enumerate(heard):
        if j in shared:
            continue
        scores = [contained(line, a) for a in approved]
        owner = max(range(len(approved)), key=scores.__getitem__)
        if scores[owner] >= PIECE_MIN:
            held[owner] = held.get(owner, 0) + negations(line, spec)
    return any(n != negations(approved[i], spec) for i, n in held.items())


def _letters(word: str) -> int:
    return sum(1 for ch in word if unicodedata.category(ch)[0] in "LM")


def reply_not_neutral(reply: str, script_text: str, spec: LanguageMarkers) -> bool:
    """The reply repeats a word (3+ letters) of the approved instruction or questions that is not
    one of the language's thanks words. In a script written without spaces (Chinese), any run of 3
    characters left once the thanks words are taken out counts as such a word."""
    thanks = {normalise(w) for w in spec.thanks_words}
    script = normalise(script_text)
    script_words = set(script.split())
    said = normalise(reply)
    if any(
        _letters(w) >= MIN_REPLY_WORD_LETTERS and w in script_words and w not in thanks
        for w in said.split()
    ):
        return True
    if spec.spaced:
        return False
    for word in sorted(thanks, key=len, reverse=True):
        if word:
            said = said.replace(word, " ")
    flat = script.replace(" ", "")
    width = MIN_REPLY_WORD_LETTERS
    return any(
        chunk[i : i + width] in flat
        for chunk in said.split()
        for i in range(len(chunk) - width + 1)
    )


# The checks ------------------------------------------------------------------------------------


def _segment_check(
    segment: str,
    said: str,
    expected: str,
    worker_ranges: Sequence[Range],
    *,
    min_script_share: float,
    min_similarity: float,
    spec: LanguageMarkers | None,
) -> DeliveryCheck:
    spoken = bool(said.strip())
    worker_share, _, _ = script_shares(said, worker_ranges)
    script_ok = spoken and worker_share >= min_script_share
    score = similarity(said, expected)
    issues: list[DeliveryIssue] = []
    if not spoken:
        issues.append("not_spoken")
    else:
        if not script_ok:
            issues.append("wrong_script")
        if score < min_similarity:
            issues.append("low_similarity")
        if spec is not None:
            if negation_changed(said, expected, spec):
                issues.append("negation_changed")
            if numbers(said, spec.number_words, spec.match) != numbers(
                expected, spec.number_words, spec.match
            ):
                issues.append("number_changed")
    return DeliveryCheck(
        segment=segment,
        similarity=score,
        script_ok=script_ok,
        ok=script_ok and score >= min_similarity and not issues,
        issues=issues,
        said=said if spoken else None,
    )


def _reply_check(
    segment: str,
    said: str,
    worker_ranges: Sequence[Range],
    *,
    min_script_share: float,
    reply_max_chars: int,
    script_text: str,
    spec: LanguageMarkers | None,
) -> DeliveryCheck:
    worker_share, _, _ = script_shares(said, worker_ranges)
    script_ok = worker_share >= min_script_share
    issues: list[DeliveryIssue] = [] if script_ok else ["wrong_script"]
    if len(normalise(said)) > reply_max_chars:
        issues.append("reply_too_long")
    if spec is not None and reply_not_neutral(said, script_text, spec):
        issues.append("reply_not_neutral")
    return DeliveryCheck(
        segment=segment,
        similarity=REPLY_SIMILARITY,
        script_ok=script_ok,
        ok=script_ok and not issues,
        issues=issues,
        said=said,
    )


def delivery_checks(
    script: Script,
    delivered: Mapping[str, str],
    worker_ranges: Sequence[Range],
    *,
    min_script_share: float,
    min_similarity: float = 0.8,
    markers: LanguageMarkers | None = None,
    reply_max_chars: int = 60,
) -> list[DeliveryCheck]:
    """One check per segment of the script, in the order it is spoken, each question followed by
    its reply when Live said one. A segment Live never spoke scores 0 and is `not_spoken`.
    Without `markers` the negation and number counts are skipped."""
    checks = []
    texts = segment_texts(script)
    approved = "\n".join([script.instruction, *(q.text for q in script.questions)])
    for segment, expected in texts.items():
        said = delivered.get(segment, "")
        checks.append(
            _segment_check(
                segment,
                said,
                expected,
                worker_ranges,
                min_script_share=min_script_share,
                min_similarity=min_similarity,
                spec=markers,
            )
        )
        reply = delivered.get(f"{segment}{REPLY_SUFFIX}", "")
        if segment not in (INSTRUCTION, CLOSING) and reply.strip():
            checks.append(
                _reply_check(
                    f"{segment}{REPLY_SUFFIX}",
                    reply,
                    worker_ranges,
                    min_script_share=min_script_share,
                    reply_max_chars=reply_max_chars,
                    script_text=approved,
                    spec=markers,
                )
            )
    return checks
