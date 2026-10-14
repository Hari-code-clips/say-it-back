"""Metric maths for the Say It Back eval. Pure functions over step-level rows (no I/O).

Definitions follow docs/API.md, "Eval report":
- exactAccuracy: predicted label equals gold. unclear is exact only against unclear gold.
- unsafeErrors: gold missed, contradicted or unclear, rated covered (any repeat counts, see Row.any_covered).
- unsafeUpperBound95: 3/N when no unsafe error is observed (rule of three); a Wilson 95% bound otherwise.
- catchRate: share of gold missed, contradicted or unclear rows not rated covered.
- overFlagRate: share of gold covered rows not rated covered.
- unclearRate: share of all predictions that are unclear.
Ratios with an empty denominator are None (JSON null), not 0.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from config import PASS_EXACT_MIN, PASS_UNSAFE_MAX

GOLD_MISS = ("missed", "contradicted", "unclear")  # a gold unclear row is a miss: the answer must not be covered
Z95 = 1.96


@dataclass(frozen=True)
class Row:
    """One step of one item. With --repeat K, pred is the unanimous verdict or unclear if repeats disagree."""

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
    return {
        "n": n,
        "exactAccuracy": ratio(sum(is_exact(r) for r in rows), n),
        "unsafeErrors": unsafe,
        "unsafeDenominator": len(gold_miss),
        "unsafeUpperBound95": unsafe_upper_bound(unsafe, len(gold_miss)),
        "catchRate": ratio(len(gold_miss) - unsafe, len(gold_miss)),
        "overFlagRate": ratio(sum(is_over_flag(r) for r in gold_covered), len(gold_covered)),
        "unclearRate": ratio(sum(r.pred == "unclear" for r in rows), n),
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
    exact = summary["exactAccuracy"]
    return exact is not None and exact >= PASS_EXACT_MIN and summary["unsafeErrors"] <= PASS_UNSAFE_MAX
