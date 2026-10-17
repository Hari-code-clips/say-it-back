"""Metric maths for the Say It Back eval. Pure functions over step-level rows (no I/O).

Definitions follow docs/API.md, "Eval report":
- exactAccuracy: predicted label equals gold. unclear is exact only against unclear gold.
- unsafeErrors: gold missed, contradicted or unclear, rated covered (any repeat counts, see Row.any_covered).
- unsafeUpperBound95: 3/N when no unsafe error is observed (rule of three); a Wilson 95% bound otherwise.
- catchRate: share of gold missed, contradicted or unclear rows not rated covered.
- overFlagRate: share of gold covered rows not rated covered.
- unclearRate: share of all predictions that are unclear (the product shows these as "Ask again").
- correctPassRate (v0.5): share of gold covered rows rated covered. With --repeat K a step counts as correctly
  passed only if every repeat rated it covered (Row.pred, the unanimous verdict); a step covered in some repeats
  and not others is not a correct pass. This is the conservative reading: it can only lower the rate.
- unsafeUpperBound95Items (v0.5): the same bound over items, not step ratings: N is the number of items with at
  least one gold-miss step (unsafeItemDenominator), and an item is an error if any of its gold-miss steps is unsafe.
  Steps of one answer are not independent, so this is the honest N for "how often would a bad answer get through".
Ratios with an empty denominator are None (JSON null), not 0. counts() gives the plain counts behind them.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from config import PASS_CORRECT_MIN, PASS_EXACT_MIN, PASS_UNSAFE_MAX

GOLD_MISS = ("missed", "contradicted", "unclear")  # a gold unclear row is a miss: the answer must not be covered
Z95 = 1.96


@dataclass(frozen=True)
class RunRating:
    """One step's final (guarded) rating in the first run of an item, kept for the report's items[].ratings."""

    step_id: str
    verdict: str
    quote: str | None = None
    quote_translation: str | None = None
    reason: str | None = None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Row:
    """One step of one item. With --repeat K, pred is the unanimous verdict or unclear if repeats disagree.

    held_out: the item is on a held-out task (v0.5). translation: the blind transcriber's English translation of
    the item's answer (first run), which the keyword baseline reads; the same on every row of an item. source
    (v0.5.1): synthetic_tts or recorded (a consented human voice). original (v0.5.1): the blind transcriber's text
    in the worker's language (first run), the same on every row of an item. rating (v0.5.1): this step's rating in
    the first run, or None when that run returned none.
    """

    item_id: str
    task_id: str
    worker_lang: str
    pattern: str
    noise: str
    step_id: str
    gold: str
    pred: str
    any_covered: bool
    flags: tuple[str, ...] = ()
    evidence: str = ""
    held_out: bool = False
    translation: str = ""
    source: str = "synthetic_tts"
    original: str = ""
    rating: RunRating | None = None


def is_gold_miss(gold: str) -> bool:
    return gold in GOLD_MISS


def is_exact(row: Row) -> bool:
    return row.pred == row.gold


def is_unsafe(row: Row) -> bool:
    return is_gold_miss(row.gold) and row.any_covered


def is_over_flag(row: Row) -> bool:
    return row.gold == "covered" and row.pred != "covered"


def ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def wilson_upper(errors: int, n: int, z: float = Z95) -> float:
    p = errors / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min(1.0, (centre + margin) / (1 + z * z / n))


def unsafe_upper_bound(errors: int, n: int) -> float | None:
    """Rule of three when there are no errors (3/N); a Wilson 95% upper bound otherwise."""
    if n == 0:
        return None
    if errors == 0:
        return 3.0 / n
    return wilson_upper(errors, n)


def summarize(rows: Sequence[Row]) -> dict:
    n = len(rows)
    gold_miss = [r for r in rows if is_gold_miss(r.gold)]
    gold_covered = [r for r in rows if r.gold == "covered"]
    unsafe = sum(is_unsafe(r) for r in rows)
    miss_items = {r.item_id for r in gold_miss}
    unsafe_items = {r.item_id for r in gold_miss if is_unsafe(r)}
    return {
        "n": n,
        "exactAccuracy": ratio(sum(is_exact(r) for r in rows), n),
        "unsafeErrors": unsafe,
        "unsafeDenominator": len(gold_miss),
        "unsafeUpperBound95": unsafe_upper_bound(unsafe, len(gold_miss)),
        "catchRate": ratio(len(gold_miss) - unsafe, len(gold_miss)),
        "overFlagRate": ratio(sum(is_over_flag(r) for r in gold_covered), len(gold_covered)),
        "unclearRate": ratio(sum(r.pred == "unclear" for r in rows), n),
        "correctPassRate": ratio(sum(r.pred == "covered" for r in gold_covered), len(gold_covered)),
        "unsafeUpperBound95Items": unsafe_upper_bound(len(unsafe_items), len(miss_items)),
        "unsafeItemDenominator": len(miss_items),
    }


def counts(rows: Sequence[Row]) -> dict:
    """Plain counts behind the ratios, in the product's words.

    falsePasses = unsafeErrors (a gold-miss step shown as "Got it"); correctPasses = gold covered rated
    covered in every repeat (pred, never any_covered); askedAgain = step ratings returned as unclear ("Ask again").
    """
    gold_covered = [r for r in rows if r.gold == "covered"]
    return {
        "stepRatings": len(rows),
        "goldMiss": sum(is_gold_miss(r.gold) for r in rows),
        "falsePasses": sum(is_unsafe(r) for r in rows),
        "goldCovered": len(gold_covered),
        "correctPasses": sum(r.pred == "covered" for r in gold_covered),
        "askedAgain": sum(r.pred == "unclear" for r in rows),
    }


def group_summary(rows: Iterable[Row], key: Callable[[Row], str]) -> dict[str, dict]:
    """Per-group n, exactAccuracy and unsafeErrors, as the report schema has them."""
    groups: dict[str, list[Row]] = {}
    for row in rows:
        groups.setdefault(key(row), []).append(row)
    out = {}
    for name in sorted(groups):
        summary = summarize(groups[name])
        out[name] = {"n": summary["n"], "exactAccuracy": summary["exactAccuracy"],
                     "unsafeErrors": summary["unsafeErrors"]}
    return out


def passes_bar(summary: dict) -> bool:
    """exact >= 0.80, no unsafe error, and correctPassRate >= 0.75 (v0.5). A ratio that cannot be measured
    (None) never meets the bar."""
    exact, correct = summary["exactAccuracy"], summary.get("correctPassRate")
    return (exact is not None and exact >= PASS_EXACT_MIN and summary["unsafeErrors"] <= PASS_UNSAFE_MAX
            and correct is not None and correct >= PASS_CORRECT_MIN)
