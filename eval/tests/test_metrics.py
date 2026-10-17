"""Metric maths on hand-built fixtures. Each test builds its rows explicitly so the expected numbers are checkable."""

import pytest

from metrics import (
    Row,
    counts,
    group_summary,
    is_exact,
    is_unsafe,
    passes_bar,
    summarize,
    unsafe_upper_bound,
    wilson_upper,
)


def make_row(gold: str, pred: str, *, any_covered: bool | None = None, lang: str = "ta",
             pattern: str = "complete") -> Row:
    covered_any = (pred == "covered") if any_covered is None else any_covered
    return Row(item_id="panel-isolation.q1.ta.complete.clean", task_id="panel-isolation",
               worker_lang=lang, pattern=pattern, noise="clean", step_id="s1",
               gold=gold, pred=pred, any_covered=covered_any)


def test_exact_accuracy_counts_only_matching_labels():
    rows = [
        make_row("covered", "covered"),
        make_row("missed", "missed"),
        make_row("contradicted", "contradicted"),
        make_row("covered", "unclear"),
        make_row("missed", "covered"),
    ]

    summary = summarize(rows)

    assert summary["exactAccuracy"] == pytest.approx(3 / 5)
    assert summary["unclearRate"] == pytest.approx(1 / 5)


def test_catch_rate_and_over_flag_rate_with_one_unsafe_error():
    rows = [
        make_row("missed", "missed"),
        make_row("missed", "unclear"),
        make_row("contradicted", "contradicted"),
        make_row("missed", "covered"),
        make_row("covered", "covered"),
        make_row("covered", "covered"),
        make_row("covered", "unclear"),
        make_row("covered", "missed"),
    ]

    summary = summarize(rows)

    assert summary["unsafeDenominator"] == 4
    assert summary["unsafeErrors"] == 1
    assert summary["catchRate"] == pytest.approx(3 / 4)
    assert summary["overFlagRate"] == pytest.approx(2 / 4)


def test_unsafe_error_is_a_gold_miss_rated_covered():
    rows = [
        make_row("contradicted", "covered"),
        make_row("contradicted", "contradicted"),
        make_row("covered", "covered"),
    ]

    assert summarize(rows)["unsafeErrors"] == 1


def test_a_repeat_that_covers_a_gold_miss_is_unsafe_even_when_repeats_disagree():
    rows = [
        make_row("missed", "unclear", any_covered=True),
        make_row("missed", "missed"),
    ]

    summary = summarize(rows)

    assert summary["unsafeErrors"] == 1
    assert summary["catchRate"] == pytest.approx(1 / 2)


def test_rule_of_three_bound_is_3_over_n_when_no_error_is_observed():
    rows = [make_row("missed", "missed") for _ in range(30)]

    summary = summarize(rows)

    assert summary["unsafeErrors"] == 0
    assert summary["unsafeUpperBound95"] == pytest.approx(3 / 30)


def test_rule_of_three_helper_and_empty_denominator():
    assert unsafe_upper_bound(0, 40) == pytest.approx(0.075)
    assert unsafe_upper_bound(0, 0) is None


def test_wilson_bound_sits_above_an_observed_error_rate():
    upper = unsafe_upper_bound(2, 40)

    assert upper == pytest.approx(wilson_upper(2, 40))
    assert 2 / 40 < upper < 1.0


def test_ratios_without_a_denominator_are_none_not_zero():
    summary = summarize([make_row("covered", "covered")])

    assert summary["catchRate"] is None
    assert summary["unsafeUpperBound95"] is None
    assert summarize([])["exactAccuracy"] is None


def test_group_summary_reports_n_exact_and_unsafe_per_language():
    rows = [
        make_row("covered", "covered", lang="ta"),
        make_row("covered", "missed", lang="ta"),
        make_row("missed", "covered", lang="bn"),
    ]

    groups = group_summary(rows, lambda row: row.worker_lang)

    assert groups["ta"] == {"n": 2, "exactAccuracy": 0.5, "unsafeErrors": 0}
    assert groups["bn"] == {"n": 1, "exactAccuracy": 0.0, "unsafeErrors": 1}


def test_gold_unclear_is_a_gold_miss_and_exact_only_against_unclear():
    rows = [make_row("unclear", "unclear"), make_row("unclear", "missed"), make_row("unclear", "covered")]

    summary = summarize(rows)

    assert summary["unsafeDenominator"] == 3
    assert summary["unsafeErrors"] == 1
    assert summary["exactAccuracy"] == pytest.approx(1 / 3)
    assert summary["catchRate"] == pytest.approx(2 / 3)


def test_gold_unclear_with_unclear_prediction_is_exact_and_safe():
    row = make_row("unclear", "unclear")

    assert is_exact(row)
    assert not is_unsafe(row)


def test_gold_unclear_with_covered_prediction_is_an_unsafe_error():
    row = make_row("unclear", "covered")

    assert is_unsafe(row)
    assert not is_exact(row)


def test_pass_bar_needs_exact_accuracy_of_at_least_80_percent_and_no_unsafe_error():
    assert passes_bar({"exactAccuracy": 0.8, "unsafeErrors": 0, "correctPassRate": 0.9})
    assert not passes_bar({"exactAccuracy": 0.79, "unsafeErrors": 0, "correctPassRate": 0.9})
    assert not passes_bar({"exactAccuracy": 0.95, "unsafeErrors": 1, "correctPassRate": 0.9})
    assert not passes_bar({"exactAccuracy": None, "unsafeErrors": 0, "correctPassRate": 0.9})


def test_pass_bar_v05_also_needs_a_correct_pass_rate_of_at_least_75_percent():
    """A checker that asks again on everything it could pass must not meet the bar on exactness alone."""
    assert passes_bar({"exactAccuracy": 0.9, "unsafeErrors": 0, "correctPassRate": 0.75})
    assert not passes_bar({"exactAccuracy": 0.9, "unsafeErrors": 0, "correctPassRate": 0.74})
    assert not passes_bar({"exactAccuracy": 0.9, "unsafeErrors": 0, "correctPassRate": None})
    assert not passes_bar({"exactAccuracy": 0.9, "unsafeErrors": 0})


def item_row(item: str, gold: str, pred: str, *, step: str = "s1", any_covered: bool | None = None) -> Row:
    covered_any = (pred == "covered") if any_covered is None else any_covered
    return Row(item_id=item, task_id="t", worker_lang="ta", pattern="complete", noise="clean", step_id=step,
               gold=gold, pred=pred, any_covered=covered_any)


FOUR_ITEMS = [
    # A: two gold misses in one answer, both rated covered: 2 unsafe step ratings, 1 unsafe item
    item_row("A", "missed", "covered", step="s1"), item_row("A", "contradicted", "covered", step="s2"),
    # B: a gold miss caught, and a gold covered passed
    item_row("B", "missed", "missed", step="s1"), item_row("B", "covered", "covered", step="s2"),
    # C: gold covered asked again, and gold covered passed
    item_row("C", "covered", "unclear", step="s1"), item_row("C", "covered", "covered", step="s2"),
    # D: no gold miss at all (not in the item denominator), gold covered missed
    item_row("D", "covered", "missed", step="s1"),
]


def test_correct_pass_rate_is_gold_covered_rated_covered_over_gold_covered():
    summary = summarize(FOUR_ITEMS)

    assert summary["correctPassRate"] == pytest.approx(2 / 4)
    assert summary["correctPassRate"] == pytest.approx(1 - summary["overFlagRate"])
    assert summarize([item_row("A", "missed", "missed")])["correctPassRate"] is None


def test_a_step_covered_in_only_some_repeats_is_not_a_correct_pass():
    """With repeats, a correct pass needs every repeat to say covered (pred), not any of them (any_covered)."""
    rows = [item_row("A", "covered", "unclear", any_covered=True),  # covered, then not: repeats disagree
            item_row("B", "covered", "covered")]

    assert summarize(rows)["correctPassRate"] == pytest.approx(1 / 2)
    assert counts(rows)["correctPasses"] == 1


def test_unsafe_bound_over_items_counts_each_answer_once():
    summary = summarize(FOUR_ITEMS)

    assert summary["unsafeErrors"] == 2 and summary["unsafeDenominator"] == 3
    assert summary["unsafeItemDenominator"] == 2  # A and B have a gold miss; C and D do not
    assert summary["unsafeUpperBound95Items"] == pytest.approx(wilson_upper(1, 2))


def test_unsafe_bound_over_items_is_rule_of_three_with_no_unsafe_item():
    rows = [item_row(f"I{n}", "missed", "missed", step=step) for n in range(10) for step in ("s1", "s2")]

    summary = summarize(rows)

    assert summary["unsafeDenominator"] == 20 and summary["unsafeUpperBound95"] == pytest.approx(3 / 20)
    assert summary["unsafeItemDenominator"] == 10 and summary["unsafeUpperBound95Items"] == pytest.approx(3 / 10)


def test_a_repeat_that_covers_counts_its_item_as_unsafe():
    rows = [item_row("A", "missed", "unclear", any_covered=True), item_row("B", "missed", "missed")]

    assert summarize(rows)["unsafeUpperBound95Items"] == pytest.approx(wilson_upper(1, 2))
