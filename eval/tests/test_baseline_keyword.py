"""The keyword baseline (plan v0.5, Task 6): what a check with no judge model would score on the same translations."""

import pytest

from baseline_keyword import all_baselines, baseline_rows, content_words, is_negated, rate
from catalog_io import load_catalog
from metrics import Row

UNDER_LOAD = {"essential": ["never go under the load"]}
BARRIER = {"essential": ["stay outside the barrier", "until the load is landed"]}


def test_the_lead_hard_case_passes_a_keyword_check_and_the_negation_variant_catches_it():
    """The plan's own example: "I'll stand under the load" has every keyword of "never go under the load"."""
    answer = "I'll stand under the load and hold it straight with my hand."

    assert rate(UNDER_LOAD, answer) == "covered"
    assert rate(UNDER_LOAD, answer, negation=True) == "contradicted"


def test_a_negated_answer_agrees_with_a_negated_essential():
    assert rate(UNDER_LOAD, "I won't go under the load.", negation=True) == "covered"
    assert rate(UNDER_LOAD, "I’ll never go under the load.", negation=True) == "covered"  # curly apostrophe


def test_the_negation_variant_reads_the_clause_that_matches_best():
    """Every clause names the load; the one that also says "go under" decides."""
    answer = ("While the load is moving I'll stand outside the barricade. I won't go in until the load is down. "
              "I'll never go under the load.")

    assert rate(UNDER_LOAD, answer, negation=True) == "covered"


def test_covered_needs_every_content_word_of_every_essential_phrase():
    assert rate(BARRIER, "I'll stay outside the barrier until the load is landed.") == "covered"
    assert rate(BARRIER, "I'll stay outside the barrier.") == "unclear"  # load and landed are missing
    assert rate(BARRIER, "I'll wait by the crane.") == "missed"


def test_no_words_at_all_is_missed_and_an_essential_of_stopwords_only_is_unclear():
    assert rate(UNDER_LOAD, "") == "missed"
    assert rate(UNDER_LOAD, "", negation=True) == "missed"
    assert rate({"essential": ["do not go"]}, "anything at all") == "unclear"


def test_content_words_drop_stopwords_negations_and_contractions_and_a_plural_s():
    assert content_words("never go under the load") == {"load"}
    assert content_words("I won't touch the wires") == {"touch", "wire"}
    assert content_words("the signalman's signals") == {"signalman", "signal"}
    assert is_negated("I won't") and is_negated("never") and not is_negated("I will")


def row(item: str, task: str, step: str, gold: str, translation: str) -> Row:
    return Row(item_id=item, task_id=task, worker_lang="ta", pattern="complete", noise="clean", step_id=step,
               gold=gold, pred="unclear", any_covered=False, flags=("judge_disagree",), evidence="quote",
               translation=translation)


def test_baseline_rows_replace_only_the_prediction_using_the_catalog_essentials():
    catalog = load_catalog()
    rows = [row("a", "lifting-zone", "s1", "contradicted", "I'll stand under the load."),
            row("b", "fragile-roof", "s3", "covered", "I'll walk only on the crawling boards.")]

    keyword = baseline_rows(rows, catalog)
    negation = baseline_rows(rows, catalog, negation=True)

    assert [r.pred for r in keyword] == ["covered", "covered"]
    assert [r.pred for r in negation] == ["contradicted", "covered"]
    assert keyword[0].any_covered is True and negation[0].any_covered is False
    assert keyword[0].flags == () and keyword[0].evidence == ""
    assert [(r.item_id, r.step_id, r.gold) for r in keyword] == [(r.item_id, r.step_id, r.gold) for r in rows]


def test_all_baselines_names_both_variants():
    rows = [row("a", "lifting-zone", "s1", "contradicted", "I'll stand under the load.")]

    found = all_baselines(rows, load_catalog())

    assert set(found) == {"keyword", "keywordNegation"}
    assert found["keyword"][0].pred == "covered" and found["keywordNegation"][0].pred == "contradicted"


@pytest.mark.parametrize("text", ["", "OK.", "Yes, I'll be careful up there."])
def test_a_vague_or_empty_answer_is_never_covered(text):
    catalog = load_catalog()
    steps = [step for task in catalog["tasks"] for step in task["referenceSteps"]]

    assert all(rate(step, text, negation=flag) != "covered" for step in steps for flag in (False, True))
