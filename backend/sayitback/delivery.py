"""Live mode: compare what Gemini Live actually said with the approved script.

`similarity` is the character-level ratio of normalised texts. `script_ok` is true when the
speech is in the worker language's own script, which catches Odia drifting to Hindi.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher

from sayitback.guards import Range, normalise, script_shares
from sayitback.models import DeliveryCheck, Script

INSTRUCTION = "instruction"
CLOSING = "closing"
REPLY_SUFFIX = (
    ".reply"  # the briefer's speech after an answer window; evidence only, never compared
)


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


def delivery_checks(
    script: Script,
    delivered: Mapping[str, str],
    worker_ranges: Sequence[Range],
    *,
    min_script_share: float,
) -> list[DeliveryCheck]:
    """One check per segment of the script. A segment Live never spoke scores 0."""
    checks = []
    for segment, expected in segment_texts(script).items():
        said = delivered.get(segment, "")
        worker_share, _, _ = script_shares(said, worker_ranges)
        checks.append(
            DeliveryCheck(
                segment=segment,
                similarity=similarity(said, expected),
                script_ok=bool(said.strip()) and worker_share >= min_script_share,
            )
        )
    return checks
