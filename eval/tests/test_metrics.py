"""Metric maths on hand-built fixtures. Each test builds its rows explicitly so the expected numbers are checkable."""

import pytest

from metrics import Row, group_summary, is_exact, is_unsafe, passes_bar, summarize, unsafe_upper_bound, wilson_upper


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
    assert passes_bar({"exactAccuracy": 0.8, "unsafeErrors": 0})
    assert not passes_bar({"exactAccuracy": 0.79, "unsafeErrors": 0})
    assert not passes_bar({"exactAccuracy": 0.95, "unsafeErrors": 1})
    assert not passes_bar({"exactAccuracy": None, "unsafeErrors": 0})
